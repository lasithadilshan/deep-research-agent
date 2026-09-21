"""Unit tests for SessionStore state persistence and export."""

from pathlib import Path

import pytest

from deep_research.models.cost import BudgetTracker
from deep_research.models.plan import ResearchMode
from deep_research.models.report import Citation, ResearchReport, Section
from deep_research.models.state import ResearchState, ResearchStatus
from deep_research.storage.session_store import SessionStore


@pytest.fixture
def temp_session_store(tmp_path: Path) -> SessionStore:
    return SessionStore(sessions_dir=tmp_path / "sessions")


def test_session_save_and_load(temp_session_store: SessionStore) -> None:
    state = ResearchState(
        session_id="ses-persist-01",
        initial_query="Quantum surface codes",
        mode=ResearchMode.STANDARD,
        budget=BudgetTracker(max_budget_usd=1.0),
        status=ResearchStatus.COMPLETED,
    )
    state.final_report = ResearchReport(
        title="Surface Codes Report",
        executive_summary="Quantum errors mitigated [1].",
        sections=[
            Section(
                title="Findings",
                content="Threshold exceeded at 99.9% [1].",
                cited_numbers=[1],
            )
        ],
        bibliography=[
            Citation(
                numeric_index=1,
                source_id="src-q1",
                url="https://arxiv.org/abs/2403.01234",
                title="Surface Codes",
                accessed_date="2026-09-21",
                verbatim_quote_anchor="99.9% threshold",
            )
        ],
    )

    path = temp_session_store.save_session(state)
    assert path.exists()

    loaded = temp_session_store.load_session("ses-persist-01")
    assert loaded.session_id == state.session_id
    assert loaded.initial_query == state.initial_query
    assert loaded.status == ResearchStatus.COMPLETED
    assert loaded.final_report is not None
    assert loaded.final_report.title == "Surface Codes Report"


def test_list_sessions(temp_session_store: SessionStore) -> None:
    state1 = ResearchState(
        session_id="ses-01",
        initial_query="Query 1",
        mode=ResearchMode.QUICK,
        budget=BudgetTracker(max_budget_usd=1.0),
    )
    state2 = ResearchState(
        session_id="ses-02",
        initial_query="Query 2",
        mode=ResearchMode.DEEP,
        budget=BudgetTracker(max_budget_usd=2.0),
    )

    temp_session_store.save_session(state1)
    temp_session_store.save_session(state2)

    sessions = temp_session_store.list_sessions()
    assert len(sessions) == 2
    ids = {s.session_id for s in sessions}
    assert ids == {"ses-01", "ses-02"}


def test_delete_session(temp_session_store: SessionStore) -> None:
    state = ResearchState(
        session_id="ses-del",
        initial_query="To be deleted",
        mode=ResearchMode.QUICK,
        budget=BudgetTracker(max_budget_usd=1.0),
    )
    temp_session_store.save_session(state)
    assert temp_session_store.delete_session("ses-del") is True
    assert temp_session_store.delete_session("ses-del") is False


def test_export_report_formats(temp_session_store: SessionStore) -> None:
    state = ResearchState(
        session_id="ses-export",
        initial_query="Export test",
        mode=ResearchMode.QUICK,
        budget=BudgetTracker(max_budget_usd=1.0),
    )
    state.final_report = ResearchReport(
        title="Export Title",
        executive_summary="Executive summary text [1].",
        sections=[Section(title="S1", content="Content [1]", cited_numbers=[1])],
        bibliography=[
            Citation(
                numeric_index=1,
                source_id="src-1",
                url="https://example.org",
                title="Source Title",
                accessed_date="2026-09-21",
                verbatim_quote_anchor="anchor",
            )
        ],
    )
    temp_session_store.save_session(state)

    md = temp_session_store.export_report("ses-export", format_type="markdown")
    assert "# Export Title" in md
    assert '[1] "Source Title"' in md

    html_doc = temp_session_store.export_report("ses-export", format_type="html")
    assert "<!DOCTYPE html>" in html_doc
    assert "<title>Export Title</title>" in html_doc
    assert 'class="citation-link"' in html_doc

    json_doc = temp_session_store.export_report("ses-export", format_type="json")
    assert '"title": "Export Title"' in json_doc
