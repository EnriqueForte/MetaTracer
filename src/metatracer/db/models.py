"""SQLModel persistence models (TASK-00, subtask 0.2.1).

Data-contract conventions:

- enum values are stored lowercase and the enums are closed sets;
- ids are str UUID4, except RawMetadataItem.id (autoincrement int);
- timestamps are timezone-aware UTC. They are declared DateTime(timezone=True)
  so PostgreSQL stores real TIMESTAMPTZ; note SQLite returns naive datetimes on
  read, and every write here is UTC â€” treat read values as UTC;
- Finding.severity stays NULL until the classifier runs â€” detectors never set it;
- no SQLite-exclusive column types, so the schema can migrate to PostgreSQL.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Index, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ReasoningDepth(StrEnum):
    brief = "brief"
    standard = "standard"
    detailed = "detailed"


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    aborted = "aborted"


class ExtractionStatus(StrEnum):
    ok = "ok"
    skipped = "skipped"
    failed = "failed"


class SkipReason(StrEnum):
    unsupported_type = "unsupported_type"
    too_large = "too_large"
    out_of_scope = "out_of_scope"
    duplicate_hash = "duplicate_hash"
    empty_body = "empty_body"


class FindingType(StrEnum):
    gps = "gps"
    email = "email"
    internal_path = "internal_path"
    software_version = "software_version"
    debug_comment = "debug_comment"


class DetectorMethod(StrEnum):
    rule = "rule"
    heuristic = "heuristic"
    agent = "agent"


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class Severity(StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class Run(SQLModel, table=True):
    __tablename__ = "run"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    target_input: str = Field(sa_type=Text)  # JSON-serialized list of targets
    allowed_scope: str = Field(sa_type=Text)  # JSON-serialized list of authorized domains
    scope_confirmed: bool = False
    reasoning_depth: ReasoningDepth = ReasoningDepth.standard
    status: RunStatus = RunStatus.pending
    started_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
    completed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    total_assets: int = 0
    total_findings: int = 0
    error_message: str | None = Field(default=None, sa_type=Text)
    # Executive paragraph written by the agent phase (TASK-05 summary node);
    # NULL when the agents did not run. ReportBuilder prefers it over the
    # heuristic hygiene note (TASK-04, 4.1.2).
    executive_summary: str | None = Field(default=None, sa_type=Text)


class Asset(SQLModel, table=True):
    __tablename__ = "asset"
    __table_args__ = (Index("ix_asset_run_id_file_hash_sha256", "run_id", "file_hash_sha256"),)

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    source_url: str
    final_url: str
    content_type: str
    file_hash_sha256: str = Field(index=True)
    file_size_bytes: int
    extraction_status: ExtractionStatus
    skip_reason: SkipReason | None = None
    error_message: str | None = None
    discovered_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


class RawMetadataItem(SQLModel, table=True):
    """One metadata key/value extracted from an asset.

    ``namespace`` is a plain string by contract (expected values: ``exif``,
    ``xmp``, ``pdfinfo``, ``iptc``, ``http``, ``html``, ``js``). ``value`` is
    always sanitized text, never bytes; extractors truncate it to ~2 KB with a
    truncation marker.
    """

    __tablename__ = "raw_metadata_item"

    id: int | None = Field(default=None, primary_key=True)  # autoincrement
    asset_id: str = Field(foreign_key="asset.id", index=True)
    namespace: str
    key: str
    value: str = Field(sa_type=Text)


class Finding(SQLModel, table=True):
    __tablename__ = "finding"
    __table_args__ = (
        UniqueConstraint("asset_id", "dedup_signature", name="uq_finding_asset_dedup"),
    )

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    asset_id: str = Field(foreign_key="asset.id", index=True)
    finding_type: FindingType
    field_source: str  # multiple deduplicated origins are joined with " | "
    evidence_snippet: str = Field(sa_type=Text)
    # sha256(f"{asset_id}:{finding_type}:{evidence_snippet.strip().lower()}")
    dedup_signature: str = Field(index=True)
    detector_method: DetectorMethod
    confidence: Confidence
    severity: Severity | None = None  # NULL until the classifier runs
    severity_justification: str | None = Field(default=None, sa_type=Text)
    impact_analysis: str | None = Field(default=None, sa_type=Text)
    remediation_advice: str | None = Field(default=None, sa_type=Text)
    # JSON-serialized array or newline-separated text; the JSON exporter materializes a list
    reproduction_steps: str | None = Field(default=None, sa_type=Text)
    # One-line report title drafted by the agent (TASK-05); NULL -> the report
    # builder falls back to its per-type template title (TASK-04, 4.2 item 1).
    title: str | None = None
    agent_model_used: str | None = None
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


class AgentLog(SQLModel, table=True):
    __tablename__ = "agent_log"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    finding_id: str = Field(foreign_key="finding.id")
    prompt_tokens: int
    completion_tokens: int
    model_name: str
    latency_ms: int
    # Structured agent output only; never the full prompt (it may contain secrets).
    raw_response: str = Field(sa_type=Text)
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


class Scope(SQLModel, table=True):
    """A named, reusable set of authorized domains (TASK-10, v2.0).

    Storage only: the matching authority stays :class:`ScopeValidator`
    (normalization, wildcards ``*.``). ``domains`` is a JSON list of
    host-normalized entries, the same shape as ``Run.allowed_scope`` — a scan
    copies the resolved domains onto the Run, so deleting or editing a Scope
    never alters persisted runs (TASK-10, subtask 10.4).
    """

    __tablename__ = "scope"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: str | None = Field(default=None, sa_type=Text)
    domains: str = Field(sa_type=Text)  # JSON list of normalized host entries
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
