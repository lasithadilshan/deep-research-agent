"""Unit tests for interactive human-in-the-loop plan review interface."""

from rich.console import Console

from deep_research.core.interactive import review_plan_interactively
from deep_research.models.plan import ResearchMode, ResearchPlan, SubQuestion


def create_sample_plan() -> ResearchPlan:
    """Helper to construct a deterministic sample plan."""
    return ResearchPlan(
        primary_objective="Investigation of Next-Generation Battery Chemistries",
        hypotheses=["Solid-state batteries will dominate automotive applications by 2030."],
        sub_questions=[
            SubQuestion(
                question_id="SQ-1",
                question="What are current solid-state battery energy density limits?",
                rationale="Assess technological ceiling",
                target_queries=["solid-state battery energy density", "solid-state wh/kg 2025"],
            ),
            SubQuestion(
                question_id="SQ-2",
                question="What are the manufacturing bottlenecks of ceramic electrolytes?",
                rationale="Understand commercialization barriers",
                target_queries=["ceramic electrolyte manufacturing scalability"],
            ),
        ],
        initial_search_queries=[
            "solid-state battery energy density",
            "solid-state wh/kg 2025",
            "ceramic electrolyte manufacturing scalability",
        ],
        planned_mode=ResearchMode.STANDARD,
        max_iterations=2,
    )


def test_interactive_direct_approval() -> None:
    plan = create_sample_plan()
    console = Console(record=True)

    inputs = ["a"]

    def fake_input(_: str) -> str:
        return inputs.pop(0)

    revised = review_plan_interactively(plan, console=console, input_fn=fake_input)
    assert revised is not None
    assert len(revised.sub_questions) == 2
    assert revised.primary_objective == plan.primary_objective


def test_interactive_cancellation() -> None:
    plan = create_sample_plan()
    console = Console(record=True)

    inputs = ["c"]

    def fake_input(_: str) -> str:
        return inputs.pop(0)

    revised = review_plan_interactively(plan, console=console, input_fn=fake_input)
    assert revised is None


def test_interactive_add_sub_question() -> None:
    plan = create_sample_plan()
    console = Console(record=True)

    inputs = [
        "+",
        "What is the safety profile of sodium-ion alternatives?",
        "Assess thermal runaway characteristics",
        "sodium-ion battery safety, sodium battery thermal runaway",
        "a",
    ]

    def fake_input(_: str) -> str:
        return inputs.pop(0)

    revised = review_plan_interactively(plan, console=console, input_fn=fake_input)
    assert revised is not None
    assert len(revised.sub_questions) == 3
    new_sq = revised.sub_questions[2]
    assert new_sq.question_id == "SQ-3"
    assert "sodium-ion" in new_sq.question
    assert "sodium battery thermal runaway" in revised.initial_search_queries


def test_interactive_remove_sub_question() -> None:
    plan = create_sample_plan()
    console = Console(record=True)

    inputs = [
        "-",
        "SQ-2",
        "a",
    ]

    def fake_input(_: str) -> str:
        return inputs.pop(0)

    revised = review_plan_interactively(plan, console=console, input_fn=fake_input)
    assert revised is not None
    assert len(revised.sub_questions) == 1
    assert revised.sub_questions[0].question_id == "SQ-1"


def test_interactive_edit_queries() -> None:
    plan = create_sample_plan()
    console = Console(record=True)

    inputs = [
        "q",
        "1",  # Add query
        "silicon anode degradation mechanisms",
        "q",
        "2",  # Remove query
        "1",  # Remove query #1
        "a",  # Approve
    ]

    def fake_input(_: str) -> str:
        return inputs.pop(0)

    revised = review_plan_interactively(plan, console=console, input_fn=fake_input)
    assert revised is not None
    assert "silicon anode degradation mechanisms" in revised.initial_search_queries
    assert "solid-state battery energy density" not in revised.initial_search_queries


def test_interactive_view_and_invalid_input_recovery() -> None:
    plan = create_sample_plan()
    console = Console(record=True)

    inputs = [
        "unknown_action",
        "v",  # View plan
        "a",  # Approve
    ]

    def fake_input(_: str) -> str:
        return inputs.pop(0)

    revised = review_plan_interactively(plan, console=console, input_fn=fake_input)
    assert revised is not None
    assert len(revised.sub_questions) == 2
