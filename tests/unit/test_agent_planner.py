"""Unit tests for PlannerAgent."""

import pytest

from deep_research.agents.planner import (
    GeneratedResearchPlan,
    GeneratedSubQuestion,
    PlannerAgent,
)
from deep_research.models.plan import ResearchMode
from deep_research.models.state import ResearchState, ResearchStatus
from deep_research.providers.llm.mock import MockLLMProvider


class TestPlannerAgent:
    @pytest.mark.asyncio
    async def test_planner_structured_generation(self) -> None:
        mock_llm = MockLLMProvider()
        expected_plan = GeneratedResearchPlan(
            primary_objective="Assess Scalability of Topological Quantum Computing",
            hypotheses=["Majorana zero modes provide hardware-level fault tolerance"],
            sub_questions=[
                GeneratedSubQuestion(
                    question_id="SQ-1",
                    question="What is the empirical evidence for non-Abelian braiding?",
                    rationale="Determine experimental validation of topological protection",
                    target_queries=[
                        "Majorana zero modes braiding experiment",
                        "non-Abelian statistics evidence",
                    ],
                ),
                GeneratedSubQuestion(
                    question_id="SQ-2",
                    question="What are the primary coherence and fabrication bottlenecks?",
                    rationale="Evaluate engineering viability",
                    target_queries=[
                        "topological qubit coherence times",
                        "nanowire fabrication disorder",
                    ],
                ),
            ],
            initial_search_queries=["topological quantum computing 2025 roadmap"],
        )
        mock_llm.queue_structured_response(expected_plan)

        state = ResearchState(
            initial_query="Scalability of Topological Quantum Computing",
            mode=ResearchMode.STANDARD,
        )

        planner = PlannerAgent(llm=mock_llm)
        result = await planner.execute(state)

        assert result.status == "completed"
        assert state.status == ResearchStatus.PLANNING
        assert state.plan is not None
        assert state.plan.primary_objective == expected_plan.primary_objective
        assert len(state.plan.sub_questions) == 2
        assert len(state.plan.initial_search_queries) >= 3
        assert state.budget.current_cost_usd > 0.0

    @pytest.mark.asyncio
    async def test_planner_fallback_on_llm_error(self) -> None:
        mock_llm = MockLLMProvider()
        mock_llm.queue_error(RuntimeError("LLM service timeout"))

        state = ResearchState(
            initial_query="Solid state battery commercialization",
            mode=ResearchMode.DEEP,
            max_iterations=4,
        )

        planner = PlannerAgent(llm=mock_llm)
        result = await planner.execute(state)

        assert result.status == "completed_fallback"
        assert state.plan is not None
        assert state.plan.primary_objective == "Solid state battery commercialization"
        assert len(state.plan.sub_questions) == 3
        assert state.plan.max_iterations == 4
        assert any(
            "Solid state battery commercialization" in sq.question
            for sq in state.plan.sub_questions
        )
