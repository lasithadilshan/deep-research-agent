"""Integration tests for session persistence and resumption."""

from pathlib import Path

import pytest

from deep_research.core.orchestrator import ResearchOrchestrator
from deep_research.models.plan import ResearchMode
from deep_research.models.state import ResearchStatus
from deep_research.providers.llm.mock import MockLLMProvider
from deep_research.providers.search.mock import MockSearchProvider
from deep_research.storage.session_store import SessionStore


@pytest.mark.asyncio
async def test_session_resume_pipeline(tmp_path: Path) -> None:
    session_store = SessionStore(sessions_dir=tmp_path / "sessions")
    mock_llm = MockLLMProvider()
    mock_search = MockSearchProvider()

    orchestrator = ResearchOrchestrator(
        llm=mock_llm,
        search_provider=mock_search,
        session_store=session_store,
    )

    query = "Breakthroughs in lithium sulfur batteries"
    # Execute quick mode
    state = await orchestrator.execute_research(
        query=query,
        mode=ResearchMode.QUICK,
    )

    assert state.status == ResearchStatus.COMPLETED
    assert state.session_id.startswith("ses-")

    # Verify session file exists on disk
    session_file = session_store._get_path(state.session_id)
    assert session_file.exists()

    # Resume completed session returns existing completed state
    resumed = await orchestrator.resume_research(state.session_id)
    assert resumed.session_id == state.session_id
    assert resumed.status == ResearchStatus.COMPLETED
    assert resumed.final_report is not None

    # Test multi-format export
    html_out = session_store.export_report(state.session_id, format_type="html")
    assert "<!DOCTYPE html>" in html_out
    assert "Lithium" in html_out or "Investigation" in html_out

    json_out = session_store.export_report(state.session_id, format_type="json")
    assert '"title"' in json_out
