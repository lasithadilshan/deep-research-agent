"""Research plan structures and query decomposition models."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ResearchMode(StrEnum):
    """Execution mode governing depth, iterations, and cost profile."""

    QUICK = "quick"  # 1 iteration, 3-5 sources, fast briefing
    STANDARD = "standard"  # 2 iterations, 8-12 sources, multi-section report
    DEEP = "deep"  # 3-5 iterations, 20+ sources, exhaustive scientific analysis


class SubQuestion(BaseModel):
    """Decomposed sub-problem or specific inquiry line."""

    question_id: str = Field(description="Unique identifier e.g. SQ-1")
    question: str = Field(description="Clear, targeted sub-question")
    rationale: str = Field(
        default="", description="Why this sub-question is needed to answer main objective"
    )
    target_queries: list[str] = Field(
        default_factory=list, description="Search queries generated to answer this sub-question"
    )
    is_answered: bool = Field(
        default=False, description="True if sufficient evidence has been gathered"
    )
    evidence_ids: list[str] = Field(
        default_factory=list, description="IDs of gathered evidence addressing this question"
    )


class ResearchPlan(BaseModel):
    """High-level blueprint formulated by PlannerAgent before web execution."""

    primary_objective: str = Field(description="Core question or research goal")
    hypotheses: list[str] = Field(
        default_factory=list, description="Initial testable hypotheses or perspectives"
    )
    sub_questions: list[SubQuestion] = Field(
        default_factory=list,
        description="Orthogonal sub-questions decomposing the primary objective",
    )
    initial_search_queries: list[str] = Field(
        default_factory=list, description="Initial batch of search queries to seed exploration"
    )
    planned_mode: ResearchMode = Field(
        default=ResearchMode.STANDARD, description="Target research mode"
    )
    max_iterations: int = Field(
        default=2, ge=1, le=10, description="Maximum iterative search loops allowed"
    )
