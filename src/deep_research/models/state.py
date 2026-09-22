"""Central typed state management for deep research sessions."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from deep_research.models.cost import BudgetTracker
from deep_research.models.evidence import ConfidenceLevel, Evidence
from deep_research.models.plan import ResearchMode, ResearchPlan
from deep_research.models.report import ResearchReport
from deep_research.models.source import Source


class ResearchStatus(StrEnum):
    """Lifecycle stages of a research session."""

    INITIALIZED = "initialized"
    PLANNING = "planning"
    SEARCHING = "searching"
    EXTRACTING = "extracting"
    ANALYZING = "analyzing"
    SYNTHESIZING = "synthesizing"
    AUDITING = "auditing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Finding(BaseModel):
    """Synthesized finding connecting multiple pieces of evidence."""

    finding_id: str = Field(description="e.g. FND-001")
    topic: str = Field(description="Sub-topic or question addressed")
    summary: str = Field(description="Consolidated analytical takeaway")
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


class StepResult(BaseModel):
    """Audit record of an individual agent execution step."""

    step_id: str = Field(default_factory=lambda: f"stp-{uuid.uuid4().hex[:8]}")
    agent_name: str
    status: str
    summary: str
    duration_ms: float = 0.0
    items_produced: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ResearchState(BaseModel):
    """Central append-only state model holding all knowledge for a research run."""

    session_id: str = Field(
        default_factory=lambda: f"ses-{uuid.uuid4().hex[:8]}",
        description="Unique identifier for the research session",
    )
    initial_query: str = Field(description="The original user research question")
    mode: ResearchMode = Field(default=ResearchMode.STANDARD)
    status: ResearchStatus = Field(default=ResearchStatus.INITIALIZED)
    current_iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=2, ge=1)
    plan: ResearchPlan | None = None
    sources: dict[str, Source] = Field(
        default_factory=dict, description="Lookup of canonical sources by source_id"
    )
    evidence_pool: dict[str, Evidence] = Field(
        default_factory=dict, description="Lookup of extracted evidence by evidence_id"
    )
    findings: list[Finding] = Field(default_factory=list)
    budget: BudgetTracker = Field(default_factory=lambda: BudgetTracker(max_budget_usd=1.0))
    final_report: ResearchReport | None = None
    unresolved_gaps: list[str] = Field(default_factory=list)
    identified_conflicts: list[str] = Field(default_factory=list)
    audit_log: list[str] = Field(default_factory=list)
    step_history: list[StepResult] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def transition_to(self, new_status: ResearchStatus, message: str = "") -> None:
        """Execute a validated lifecycle state transition with audit trail."""
        old_status = self.status
        self.status = new_status
        self.updated_at = datetime.utcnow()
        log_entry = f"[{self.updated_at.isoformat()}] State transition: {old_status.value} -> {new_status.value}"
        if message:
            log_entry += f" ({message})"
        self.audit_log.append(log_entry)

    def add_source(self, source: Source) -> bool:
        """Add source if not already present. Returns True if newly added, False if duplicate."""
        if source.source_id in self.sources:
            return False
        self.sources[source.source_id] = source
        self.updated_at = datetime.utcnow()
        return True

    def add_evidence(self, evidence: Evidence) -> bool:
        """Add evidence item. Returns True if newly added, False if duplicate."""
        if evidence.evidence_id in self.evidence_pool:
            return False
        self.evidence_pool[evidence.evidence_id] = evidence
        self.updated_at = datetime.utcnow()
        return True

    def record_step(self, step: StepResult) -> None:
        """Record an agent execution result."""
        self.step_history.append(step)
        self.updated_at = datetime.utcnow()

    def record_audit(self, message: str) -> None:
        """Append an entry to the audit log."""
        timestamp = datetime.utcnow().isoformat()
        self.audit_log.append(f"[{timestamp}] {message}")
        self.updated_at = datetime.utcnow()
