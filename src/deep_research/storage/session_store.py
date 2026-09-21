"""Session state persistence and checkpoint manager."""

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from deep_research.config.settings import get_settings
from deep_research.core.exceptions import DeepResearchError, SessionNotFoundError
from deep_research.models.plan import ResearchMode
from deep_research.models.state import ResearchState, ResearchStatus


class SessionSummary(BaseModel):
    """Metadata summary of a saved research session."""

    session_id: str
    initial_query: str
    mode: ResearchMode
    status: ResearchStatus
    sources_count: int = 0
    evidence_count: int = 0
    cost_usd: float = 0.0
    has_report: bool = False
    saved_at: datetime = Field(default_factory=datetime.utcnow)


class SessionStore:
    """Manages disk serialization, listing, and resumption of research sessions."""

    def __init__(self, sessions_dir: Path | None = None) -> None:
        if sessions_dir is not None:
            self.sessions_dir = sessions_dir
        else:
            settings = get_settings()
            self.sessions_dir = settings.cache_dir.parent / "sessions"

        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, session_id: str) -> Path:
        clean_id = session_id.strip()
        if not clean_id.startswith("ses-"):
            clean_id = f"ses-{clean_id}"
        return self.sessions_dir / f"{clean_id}.json"

    def save_session(self, state: ResearchState) -> Path:
        """Serialize ResearchState to formatted JSON file on disk."""
        path = self._get_path(state.session_id)
        temp_path = path.with_suffix(".tmp")

        json_str = state.model_dump_json(indent=2)
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(json_str)

        # Atomic replacement
        temp_path.replace(path)
        return path

    def load_session(self, session_id: str) -> ResearchState:
        """Load and deserialize ResearchState from disk."""
        path = self._get_path(session_id)
        if not path.exists():
            raise SessionNotFoundError(f"Session '{session_id}' not found at {path}.")

        with open(path, encoding="utf-8") as f:
            raw_json = f.read()

        return ResearchState.model_validate_json(raw_json)

    def list_sessions(self, limit: int = 50) -> list[SessionSummary]:
        """List all saved sessions sorted newest first."""
        summaries: list[SessionSummary] = []
        for file in self.sessions_dir.glob("ses-*.json"):
            try:
                with open(file, encoding="utf-8") as f:
                    data = json.load(f)

                session_id = data.get("session_id", file.stem)
                query = data.get("initial_query", "Unknown Query")
                mode = ResearchMode(data.get("mode", "standard"))
                status = ResearchStatus(data.get("status", "completed"))
                sources = len(data.get("sources", {}))
                evidence = len(data.get("evidence_pool", {}))
                budget = data.get("budget", {})
                cost = float(budget.get("current_cost_usd", 0.0))
                has_rep = data.get("final_report") is not None

                mtime = datetime.fromtimestamp(file.stat().st_mtime)

                summaries.append(
                    SessionSummary(
                        session_id=session_id,
                        initial_query=query,
                        mode=mode,
                        status=status,
                        sources_count=sources,
                        evidence_count=evidence,
                        cost_usd=cost,
                        has_report=has_rep,
                        saved_at=mtime,
                    )
                )
            except Exception:
                continue

        summaries.sort(key=lambda s: s.saved_at, reverse=True)
        return summaries[:limit]

    def delete_session(self, session_id: str) -> bool:
        """Delete a saved session from disk."""
        path = self._get_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def export_report(self, session_id: str, format_type: str = "markdown") -> str:
        """Export final report for a session in markdown, html, or json."""
        state = self.load_session(session_id)
        if not state.final_report:
            raise DeepResearchError(f"Session '{session_id}' does not have a completed report.")

        fmt = format_type.lower().strip()
        if fmt == "html":
            return state.final_report.to_html()
        if fmt == "json":
            return state.final_report.to_json()
        return state.final_report.to_markdown()
