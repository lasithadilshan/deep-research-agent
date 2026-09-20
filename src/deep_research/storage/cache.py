"""Deterministic SQLite disk-backed caching layer with TTL expiration."""

import hashlib
import sqlite3
import threading
import time
from pathlib import Path

from deep_research.config.logging import get_logger
from deep_research.models.search import SearchResponse
from deep_research.models.source import canonicalize_url


class ResearchCache:
    """Thread-safe SQLite persistent cache for search hits and fetched web content."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        default_ttl_hours: float = 72.0,
    ) -> None:
        self.logger = get_logger("ResearchCache")
        self.default_ttl_hours = default_ttl_hours
        self._lock = threading.Lock()

        if db_path is None or str(db_path) == ":memory:":
            self.db_path_str = ":memory:"
        else:
            path_obj = Path(db_path).resolve()
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            self.db_path_str = str(path_obj)

        self._conn = sqlite3.connect(
            self.db_path_str,
            check_same_thread=False,
            timeout=30.0,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """Initialize schema and enable WAL journaling for high concurrency."""
        with self._lock:
            cursor = self._conn.cursor()
            if self.db_path_str != ":memory:":
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA synchronous=NORMAL;")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_namespace ON cache_entries(namespace);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_expires_at ON cache_entries(expires_at);"
            )
            self._conn.commit()

    @staticmethod
    def hash_key(namespace: str, raw_key: str) -> str:
        """Derive a deterministic SHA-256 cache key."""
        content = f"{namespace}:{raw_key.strip()}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get(self, namespace: str, raw_key: str) -> str | None:
        """Retrieve payload if present and unexpired, otherwise None."""
        key = self.hash_key(namespace, raw_key)
        now = time.time()

        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT payload, expires_at FROM cache_entries WHERE cache_key = ?",
                (key,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            payload, expires_at = row["payload"], row["expires_at"]
            if now > expires_at:
                # Expired - remove immediately
                cursor.execute("DELETE FROM cache_entries WHERE cache_key = ?", (key,))
                self._conn.commit()
                return None

            return str(payload)

    def set(
        self,
        namespace: str,
        raw_key: str,
        payload: str,
        ttl_hours: float | None = None,
    ) -> None:
        """Insert or replace cache entry with TTL."""
        key = self.hash_key(namespace, raw_key)
        now = time.time()
        effective_ttl = ttl_hours if ttl_hours is not None else self.default_ttl_hours
        expires_at = now + (effective_ttl * 3600.0)

        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO cache_entries
                (cache_key, namespace, payload, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key, namespace, payload, now, expires_at),
            )
            self._conn.commit()

    def delete(self, namespace: str, raw_key: str) -> bool:
        """Delete specific cache entry."""
        key = self.hash_key(namespace, raw_key)
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM cache_entries WHERE cache_key = ?", (key,))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            return deleted

    def get_search(self, provider: str, query: str, max_results: int) -> SearchResponse | None:
        """Retrieve cached search response."""
        search_key = f"{provider}:{query.strip().lower()}:{max_results}"
        payload = self.get(namespace="search", raw_key=search_key)
        if not payload:
            return None

        try:
            return SearchResponse.model_validate_json(payload)
        except Exception as e:
            self.logger.warning("cache_search_deserialization_failed", error=str(e))
            self.delete(namespace="search", raw_key=search_key)
            return None

    def set_search(
        self,
        provider: str,
        query: str,
        max_results: int,
        response: SearchResponse,
        ttl_hours: float | None = None,
    ) -> None:
        """Cache serialized search response."""
        search_key = f"{provider}:{query.strip().lower()}:{max_results}"
        self.set(
            namespace="search",
            raw_key=search_key,
            payload=response.model_dump_json(),
            ttl_hours=ttl_hours,
        )

    def get_web(self, url: str) -> str | None:
        """Retrieve cached web page content."""
        canon = canonicalize_url(url)
        return self.get(namespace="web", raw_key=canon)

    def set_web(self, url: str, content: str, ttl_hours: float | None = None) -> None:
        """Cache web page content keyed by canonical URL."""
        canon = canonicalize_url(url)
        self.set(namespace="web", raw_key=canon, payload=content, ttl_hours=ttl_hours)

    def clear(self, namespace: str | None = None) -> int:
        """Clear cache entries across a namespace or entirely."""
        with self._lock:
            cursor = self._conn.cursor()
            if namespace:
                cursor.execute("DELETE FROM cache_entries WHERE namespace = ?", (namespace,))
            else:
                cursor.execute("DELETE FROM cache_entries")
            deleted_count = cursor.rowcount
            self._conn.commit()
            return deleted_count

    def purge_expired(self) -> int:
        """Purge all expired entries across all namespaces."""
        now = time.time()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM cache_entries WHERE expires_at <= ?", (now,))
            purged = cursor.rowcount
            self._conn.commit()
            return purged

    def count(self, namespace: str | None = None) -> int:
        """Count active (unexpired) entries."""
        now = time.time()
        with self._lock:
            cursor = self._conn.cursor()
            if namespace:
                cursor.execute(
                    "SELECT COUNT(*) FROM cache_entries WHERE namespace = ? AND expires_at > ?",
                    (namespace, now),
                )
            else:
                cursor.execute(
                    "SELECT COUNT(*) FROM cache_entries WHERE expires_at > ?",
                    (now,),
                )
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def close(self) -> None:
        """Close SQLite database connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
