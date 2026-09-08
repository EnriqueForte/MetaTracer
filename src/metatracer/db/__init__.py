"""Persistence layer: async engine, SQLModel models and CRUD repositories."""

from metatracer.db.engine import (
    DEFAULT_DATABASE_URL,
    create_db_engine,
    create_session_factory,
    init_db,
)
from metatracer.db.models import (
    AgentLog,
    Asset,
    Confidence,
    DetectorMethod,
    ExtractionStatus,
    Finding,
    FindingType,
    RawMetadataItem,
    ReasoningDepth,
    Run,
    RunStatus,
    Severity,
    SkipReason,
)
from metatracer.db.repositories import (
    AgentLogRepository,
    AssetRepository,
    FindingRepository,
    RawMetadataRepository,
    RunRepository,
)

__all__ = [
    "DEFAULT_DATABASE_URL",
    "AgentLog",
    "AgentLogRepository",
    "Asset",
    "AssetRepository",
    "Confidence",
    "DetectorMethod",
    "ExtractionStatus",
    "Finding",
    "FindingRepository",
    "FindingType",
    "RawMetadataItem",
    "RawMetadataRepository",
    "ReasoningDepth",
    "Run",
    "RunRepository",
    "RunStatus",
    "Severity",
    "SkipReason",
    "create_db_engine",
    "create_session_factory",
    "init_db",
]
