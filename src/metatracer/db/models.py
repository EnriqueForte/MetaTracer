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

import random
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Index, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def _new_uuid() -> str:
    return str(uuid.uuid4())


# Human-readable run references for reports / webhooks / URLs. The RNG is
# fully recoverable (not cryptographic), so these are public identifiers only:
# never use them as tokens or for access control.
_RUN_REF_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ"
_RUN_REF_LEN = 10


def _new_run_ref() -> str:
    """Non-guessable-*looking* public tag; uniqueness enforced by DB index."""
    alphabet = _RUN_REF_ALPHABET
    rand = random.SystemRandom()
    return "".join(rand.choice(alphabet) for _ in range(_RUN_REF_LEN))


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


class FeedbackVote(StrEnum):
    """Operator correction direction (TASK-13, v2.1+).

    ``up`` means the human considers the finding more severe than the model
    said; ``down`` means less severe. Values are the lowercase wire strings.
    """

    up = "up"
    down = "down"


class Run(SQLModel, table=True):
    __tablename__ = "run"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    # Short human-readable tag for reports/URLs/webhooks (TASK-15, v2.2):
    # derived public identifier, not a security token. Unique + indexed.
    # Python default_factory generates the value for every new insert. On an
    # existing database the init_db hook adds this column as NULLABLE (the
    # ADD COLUMN of a NOT-NULL-without-constant-default otherwise breaks a
    # non-empty table); new rows always carry the generated value, and old
    # rows read NULL until an offline backfill normalizes them (see TASK-15).
    run_ref: str = Field(
        default_factory=_new_run_ref,
        index=True,
        unique=True,
        sa_column_kwargs={"nullable": False},
    )
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


# Severity has no plain order on the wire; ``_SEVERITY_RANK`` exists for the
# feedback vote validation (TASK-13): same five levels, from info -> critical.
_SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def severity_rank(severity: Severity | str) -> int:
    """Numeric rank of a severity, ``info`` (0) to ``critical`` (4).

    Falls back to 0 for unknown/empty input so a corrupt row never crashes
    the feedback endpoint — the caller still validates the truth.
    """
    key = str(severity)
    return _SEVERITY_RANK.get(key, 0)


class FindingFeedback(SQLModel, table=True):
    """One operator correction over a finding's severity (TASK-13, v2.1+).

    This is the memory of the feedback loop: each row is a small example
    ("this GPS was over-rated → down to medium") that later runs can reuse as
    few-shot guidance for findings of the same type. Rules:

    - one active row per ``finding_id`` (upsert semantics in the repository);
    - ``vote`` direction must match ``severity_after`` vs. the finding's
      current severity (validated by the API layer, not here);
    - ``reason`` is operator-only context — it never travels to the LLM, only
      the structured fields (finding type, evidence snippet, before/after) do;
    - ``reason`` is truncated to ~150 chars at the API edge (defense in depth).
    """

    __tablename__ = "finding_feedback"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    finding_id: str = Field(foreign_key="finding.id", index=True, unique=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    vote: FeedbackVote
    severity_before: Severity
    severity_after: Severity
    reason: str | None = Field(default=None, sa_type=Text)
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


class WebhookDeliveryStatus(StrEnum):
    """Per-delivery attempt status of an outbound webhook (TASK-15, v2.2)."""

    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    rejected = "rejected"


class WebhookConfig(SQLModel, table=True):
    """One outbound HTTP(S) webhook subscribed to run-terminal events.

    Created by the operator through the CLI/API; the recipient must be an
    HTTPS URL. On a terminal event the orchestrator's ``WebhookDispatcher``
    POSTs a payload built from the fixed key set ``PAYLOAD_KEYS`` (counters +
    run metadata) — there is no operator-editable template, so the payload can
    never accidentally carry raw metadata.

    Privacy/safety posture:

    - the URL and each header value are sanitized in logs; the signature
      secret is stored as SHA-256 local hash, so the plaintext secret never
      leaves the CLI/API edge and cannot be read back from the database;
    - the payload carries only structured counters and the summary — never
      file bytes, never raw metadata values;
    - deliveries are persisted into :class:`WebhookDelivery` (relay buffer)
      and are retried with a cap; a failing webhook never fails a scan.
    """

    __tablename__ = "webhook_config"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    name: str = Field(default=None, max_length=80)  # "name" is not reserved in SQL
    url: str = Field(sa_type=Text)  # HTTPS URL; validated at write time
    event: RunStatus = RunStatus.completed  # subscription: one terminal status
    headers: str = Field(default="{}", sa_type=Text)  # JSON dict name -> value
    signature_secret_hash: str | None = Field(default=None, sa_type=Text)
    max_retries: int = 3
    active: bool = True
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


class WebhookDelivery(SQLModel, table=True):
    """Persisted delivery state of one terminal event to one webhook (TASK-15).

    The relay buffer: a delivery is idempotent by ``(webhook_id, run_id)`` so
    crash/retry replays cannot double-send the same event. ``payload_json`` is
    cached so retries re-send the exact same body without re-running the
    report pipeline. ``last_error`` is the sanitized failure message.
    """

    __tablename__ = "webhook_delivery"
    __table_args__ = (
        UniqueConstraint("webhook_id", "run_id", name="uq_webhook_delivery_run"),
    )

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    webhook_id: str = Field(foreign_key="webhook_config.id", index=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    status: WebhookDeliveryStatus = WebhookDeliveryStatus.pending
    attempts: int = 0  # incremented before each HTTP attempt
    max_retries: int = 3
    payload_json: str = Field(sa_type=Text)
    status_code: int | None = None
    # Unix timestamp (s) of the next allowed attempt; the dispatcher retries
    # with backoff when due. NULL once terminal (succeeded / rejected).
    # SQLModel infers FLOAT from the ``float`` annotation (no explicit type_:
    # passing sa_column_kwargs={"type_": ...} here duplicates the type and
    # breaks model import with "May not pass type_ positionally and as keyword").
    next_retry_at: float | None = Field(default=None)
    last_error: str | None = Field(default=None, sa_type=Text)  # sanitized
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# NOTE (TASK-15): no payload-template table. The outbound payload uses a fixed
# key set (PAYLOAD_KEYS in metatracer.api.webhooks), which is safer and simpler
# than operator-editable templates: the payload can never carry unexpected raw
# metadata. A future slice could add a template table if a use case requires it.


class UserRole(StrEnum):
    """Role of the single installation user (TASK-24, v3.0 Eje C).

    ``operator`` can do everything (create scopes, launch scans, feedback,
    webhooks). ``viewer`` is read-only (dashboards, reports, exports). Values
    are the lowercase wire strings, like every other closed enum.
    """

    operator = "operator"
    viewer = "viewer"


class User(SQLModel, table=True):
    """The single installation user (TASK-24, v3.0 Eje C).

    v3.0 keeps one user per installation (multi-tenant is deferred to v3.1):
    the table exists, the app only provisions one operator row (created on
    first boot from ``METATRACER_AUTH_PASSWORD``).

    Password hashing is stdlib-only (supply-chain review 2026-09-18): PBKDF2-
    HMAC-SHA256 with 600k iterations, stored self-describing and versioned as
    ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>`` so a future
    rehash-on-login can raise the cost without a schema migration.
    ``password_hash`` never leaves the database (no API response exposes it).
    """

    __tablename__ = "user"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str = Field(sa_type=Text)
    role: UserRole = UserRole.operator
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


class UserSession(SQLModel, table=True):
    """One server-side session (TASK-24): a random token, hashed at rest.

    Only the SHA-256 of the session token is stored, so a database leak never
    yields a usable cookie. Sessions expire (``expires_at`` checked in
    ``get_current_user``, not only in the cookie) and are rotated on every
    login — the fresh login invalidates the previous session (anti-fixation).
    """

    __tablename__ = "user_session"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)  # ON DELETE CASCADE (migration)
    token_hash: str = Field(unique=True, index=True)  # sha256 hex of the token
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
