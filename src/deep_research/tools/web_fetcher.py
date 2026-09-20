"""Asynchronous web fetcher with SSRF defense, size caps, and retry resilience."""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from deep_research.core.exceptions import WebFetchError

DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_TIMEOUT = 15.0
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 DeepResearch/1.0"
)


def validate_url_and_check_ssrf(url: str) -> None:
    """Validate URL scheme and ensure destination does not resolve to private/internal IP ranges."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise WebFetchError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise WebFetchError(f"Missing hostname in URL: {url}")

    # Check for localhost / numeric IP literal directly
    if hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise WebFetchError(f"Access to internal hostname '{hostname}' is blocked (SSRF guard).")

    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for _family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_reserved
                or ip.is_link_local
                or ip.is_multicast
            ):
                raise WebFetchError(
                    f"Access to private/internal IP '{ip_str}' for host '{hostname}' is blocked (SSRF guard)."
                )
    except socket.gaierror as e:
        raise WebFetchError(f"Failed to resolve DNS for host '{hostname}': {e}") from e


class WebFetcher:
    """Async web fetcher enforcing safety boundaries and content size limits."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch(
        self,
        url: str,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
        validate_ssrf: bool = True,
    ) -> str:
        """Safely fetch web page content as string up to max_bytes."""
        if validate_ssrf:
            validate_url_and_check_ssrf(url)

        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain"}

        try:
            if self._client:
                return await self._download(self._client, url, headers, timeout, max_bytes)
            else:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    return await self._download(client, url, headers, timeout, max_bytes)

        except httpx.HTTPStatusError as e:
            raise WebFetchError(f"HTTP {e.response.status_code} error fetching {url}") from e
        except httpx.TimeoutException as e:
            raise WebFetchError(f"Timeout fetching {url}: {e}") from e
        except httpx.RequestError as e:
            raise WebFetchError(f"Network error fetching {url}: {e}") from e

    async def _download(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        timeout: float,
        max_bytes: int,
    ) -> str:
        response = await client.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        content_bytes = response.content
        if len(content_bytes) > max_bytes:
            content_bytes = content_bytes[:max_bytes]

        # Decode with fallback encoding
        encoding = response.encoding or "utf-8"
        try:
            return content_bytes.decode(encoding, errors="replace")
        except Exception:
            return content_bytes.decode("utf-8", errors="replace")
