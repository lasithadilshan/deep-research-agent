"""Abstract base class for all research agents."""

import time
from abc import ABC, abstractmethod
from typing import Any

from deep_research.config.logging import get_logger
from deep_research.models.state import ResearchState, StepResult
from deep_research.providers.llm.base import BaseLLMProvider


class BaseAgent(ABC):
    """Abstract agent contract defining inputs, outputs, and execution lifecycle."""

    def __init__(self, agent_name: str, llm: BaseLLMProvider | None = None) -> None:
        self.agent_name = agent_name
        self.llm = llm
        self.logger = get_logger(agent_name)

    @abstractmethod
    async def run(self, state: ResearchState, **kwargs: Any) -> StepResult:
        """Core execution logic implemented by subclass."""
        pass

    async def execute(self, state: ResearchState, **kwargs: Any) -> StepResult:
        """Template method wrapping agent execution with timing, logging, and error handling."""
        self.logger.info("agent_started", agent=self.agent_name, session_id=state.session_id)
        start_time = time.perf_counter()

        try:
            result = await self.run(state, **kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000
            result.duration_ms = round(duration_ms, 2)
            state.record_step(result)
            self.logger.info(
                "agent_completed",
                agent=self.agent_name,
                duration_ms=result.duration_ms,
                items_produced=result.items_produced,
            )
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.logger.error("agent_failed", agent=self.agent_name, error=str(e))
            fail_step = StepResult(
                agent_name=self.agent_name,
                status="failed",
                summary=f"Agent failed with error: {e}",
                duration_ms=round(duration_ms, 2),
                items_produced=0,
            )
            state.record_step(fail_step)
            raise
