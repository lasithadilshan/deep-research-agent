"""Central workflow orchestrator coordinating multi-agent research pipelines."""

from typing import Any

from deep_research.agents.analyst import AnalystAgent
from deep_research.agents.auditor import CitationAuditorAgent
from deep_research.agents.evaluator import EvaluatorAgent
from deep_research.agents.extractor import ExtractorAgent
from deep_research.agents.planner import PlannerAgent
from deep_research.agents.synthesizer import SynthesizerAgent
from deep_research.config.logging import get_logger
from deep_research.config.settings import Settings, get_settings
from deep_research.core.exceptions import ConfigurationError
from deep_research.models.cost import BudgetTracker
from deep_research.models.plan import ResearchMode
from deep_research.models.search import SearchResponse
from deep_research.models.source import Source, canonicalize_url, generate_source_id
from deep_research.models.state import ResearchState, ResearchStatus
from deep_research.providers.llm.base import BaseLLMProvider
from deep_research.providers.llm.factory import get_llm_provider
from deep_research.providers.search.base import BaseSearchProvider
from deep_research.providers.search.factory import get_search_provider
from deep_research.storage.cache import ResearchCache
from deep_research.tools.content_cleaner import clean_html_to_markdown
from deep_research.tools.web_fetcher import WebFetcher


class ResearchOrchestrator:
    """Coordinates research inquiries across planning, discovery, extraction, and synthesis."""

    def __init__(
        self,
        llm: BaseLLMProvider | None = None,
        search_provider: BaseSearchProvider | None = None,
        settings: Settings | None = None,
        cache: ResearchCache | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.logger = get_logger("ResearchOrchestrator")

        # Resolve Cache layer
        if cache is not None:
            self.cache: ResearchCache | None = cache
        elif self.settings.cache_enabled:
            cache_db = self.settings.cache_dir / "cache.db"
            self.cache = ResearchCache(
                db_path=cache_db,
                default_ttl_hours=float(self.settings.cache_expiration_hours),
            )
        else:
            self.cache = None

        # Resolve LLM provider
        if llm:
            self.llm = llm
        else:
            provider_name = "gemini" if self.settings.gemini_api_key else "mock"
            self.llm = get_llm_provider(
                provider_name,
                api_key=self.settings.gemini_api_key,
                model_name=self.settings.gemini_model,
            )

        # Resolve Search provider
        if search_provider:
            self.search_provider = search_provider
        else:
            s_name = self.settings.default_search_provider
            try:
                self.search_provider = get_search_provider(
                    s_name,
                    api_key=self.settings.tavily_api_key if s_name == "tavily" else None,
                )
            except ConfigurationError:
                self.logger.warning(
                    "configured_search_provider_unavailable_falling_back",
                    provider=s_name,
                    fallback="duckduckgo",
                )
                self.search_provider = get_search_provider("duckduckgo")

        self.web_fetcher = WebFetcher(cache=self.cache)

        # Initialize agents
        self.planner = PlannerAgent(llm=self.llm)
        self.evaluator = EvaluatorAgent()
        self.extractor = ExtractorAgent(llm=self.llm)
        self.analyst = AnalystAgent(llm=self.llm)
        self.synthesizer = SynthesizerAgent(llm=self.llm)
        self.auditor = CitationAuditorAgent()

    async def execute_research(
        self,
        query: str,
        mode: ResearchMode | None = None,
        max_budget_usd: float | None = None,
        status_callback: Any = None,
    ) -> ResearchState:
        """Run the end-to-end research loop from query to cited report."""
        active_mode = mode or self.settings.default_research_mode
        budget_limit = max_budget_usd or self.settings.max_budget_usd_per_run

        state = ResearchState(
            initial_query=query,
            mode=active_mode,
            budget=BudgetTracker(max_budget_usd=budget_limit),
            max_iterations=(
                1
                if active_mode == ResearchMode.QUICK
                else 2
                if active_mode == ResearchMode.STANDARD
                else self.settings.max_deep_research_iterations
            ),
        )

        self.logger.info(
            "research_session_started",
            query=query,
            mode=active_mode.value,
            budget=budget_limit,
            session_id=state.session_id,
        )

        # 1. Planning Phase
        if status_callback:
            status_callback("Planning research strategy and sub-questions...")
        await self.planner.execute(state)

        # Multi-Iteration Deep Research Loop
        queries_to_search: list[str] = (
            state.plan.initial_search_queries if state.plan else [state.initial_query]
        )
        searched_queries: set[str] = set()

        for iteration in range(1, state.max_iterations + 1):
            state.current_iteration = iteration

            # Deduplicate search queries
            current_queries = [q for q in queries_to_search if q not in searched_queries]
            if not current_queries and iteration > 1:
                state.record_audit(
                    f"Iteration {iteration}: No new queries to execute; ending deep loop."
                )
                break

            for q in current_queries:
                searched_queries.add(q)

            # 2. Search & Retrieval Phase
            if status_callback:
                status_callback(
                    f"Iteration {iteration}/{state.max_iterations}: Searching web sources..."
                )
            await self._discover_and_ingest_sources(
                state, queries=current_queries, status_callback=status_callback
            )

            # 3. Source Quality & Credibility Evaluation
            if status_callback:
                status_callback(
                    f"Iteration {iteration}/{state.max_iterations}: Evaluating source credibility..."
                )
            await self.evaluator.execute(state)

            # 4. Atomic Grounded Evidence Extraction
            if status_callback:
                status_callback(
                    f"Iteration {iteration}/{state.max_iterations}: Extracting atomic factual evidence..."
                )
            await self.extractor.execute(state)

            # 5. Cross-Evidence Analysis & Gap Detection (for multi-iteration runs)
            if state.max_iterations > 1:
                if status_callback:
                    status_callback(
                        f"Iteration {iteration}/{state.max_iterations}: Analyzing evidence density & gaps..."
                    )
                await self.analyst.execute(state)

                # Check termination conditions:
                if state.budget.is_exceeded:
                    state.record_audit("Deep iteration stopped: budget ceiling exceeded.")
                    break

                if iteration >= state.max_iterations:
                    break

                sub_questions = state.plan.sub_questions if state.plan else []
                all_answered = bool(sub_questions) and all(sq.is_answered for sq in sub_questions)

                follow_ups: list[str] = []
                if self.analyst.last_analysis:
                    follow_ups.extend(self.analyst.last_analysis.suggested_follow_up_queries)
                    for conflict in self.analyst.last_analysis.conflicts:
                        if (
                            conflict.resolution_query
                            and conflict.resolution_query not in follow_ups
                        ):
                            follow_ups.append(conflict.resolution_query)

                if all_answered and not follow_ups:
                    state.record_audit(
                        "Early termination: all sub-questions satisfied with high confidence."
                    )
                    break

                if not follow_ups:
                    state.record_audit(
                        "Iteration completed: no further follow-up queries proposed."
                    )
                    break

                queries_to_search = follow_ups

        # 6. Report Synthesis
        if status_callback:
            status_callback("Synthesizing multi-section scientific report...")
        await self.synthesizer.execute(state)
        draft = self.synthesizer.last_draft

        # 7. Citation Audit & Anti-Hallucination Barrier
        if status_callback:
            status_callback("Auditing citations and compiling bibliography...")
        await self.auditor.execute(state, draft_report=draft)

        self.logger.info(
            "research_session_completed",
            session_id=state.session_id,
            sources_count=len(state.sources),
            evidence_count=len(state.evidence_pool),
            total_cost_usd=state.budget.current_cost_usd,
        )

        return state

    async def _discover_and_ingest_sources(
        self,
        state: ResearchState,
        queries: list[str] | None = None,
        status_callback: Any = None,
    ) -> None:
        """Execute queries and ingest web page content into state.sources."""
        state.transition_to(ResearchStatus.SEARCHING, "Executing web searches")
        raw_queries = queries or (
            state.plan.initial_search_queries if state.plan else [state.initial_query]
        )

        # Limit queries based on settings
        max_q = min(len(raw_queries), self.settings.max_search_queries_per_iteration)
        target_queries = raw_queries[:max_q]

        for query_str in target_queries:
            if state.budget.is_exceeded:
                state.record_audit("Search halted: budget ceiling exceeded.")
                break

            try:
                search_response: SearchResponse | None = None
                if self.cache:
                    search_response = self.cache.get_search(
                        provider=self.search_provider.provider_name,
                        query=query_str,
                        max_results=self.settings.max_sources_per_query,
                    )
                    if search_response:
                        state.record_audit(f"Retrieved cached search results for '{query_str}'")

                if not search_response:
                    search_response = await self.search_provider.search(
                        query=query_str,
                        max_results=self.settings.max_sources_per_query,
                    )
                    state.budget.record_search_call(
                        cost_usd=0.01 if self.search_provider.provider_name == "tavily" else 0.0
                    )
                    if self.cache:
                        self.cache.set_search(
                            provider=self.search_provider.provider_name,
                            query=query_str,
                            max_results=self.settings.max_sources_per_query,
                            response=search_response,
                        )

                for hit in search_response.results:
                    # Skip hit if source is already ingested
                    canon_url = canonicalize_url(hit.url)
                    src_id = generate_source_id(canon_url)
                    if src_id in state.sources:
                        continue

                    # Ingest source
                    cleaned_markdown = hit.direct_markdown or ""

                    if not cleaned_markdown and not self.search_provider.supports_direct_content():
                        # Fetch web page asynchronously if search engine doesn't return markdown
                        try:
                            raw_html = await self.web_fetcher.fetch(
                                hit.url, timeout=10.0, validate_ssrf=True
                            )
                            cleaned_markdown = clean_html_to_markdown(raw_html, base_url=hit.url)
                        except Exception as fetch_err:
                            self.logger.warning(
                                "web_fetch_skipped", url=hit.url, error=str(fetch_err)
                            )
                            cleaned_markdown = hit.snippet

                    source = Source.create(
                        url=hit.url,
                        title=hit.title,
                        snippet=hit.snippet,
                        cleaned_markdown=cleaned_markdown or hit.snippet,
                    )
                    state.add_source(source)

            except Exception as e:
                self.logger.warning("search_query_failed", query=query_str, error=str(e))
                state.record_audit(f"Search failed for '{query_str}': {e}")
