"""CRUD repositories: persistence only — no business logic in this layer."""

import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, or_, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.core.exceptions import AmbiguousRunError, RunNotFoundError
from metatracer.core.safety.scope import normalize_host
from metatracer.db.models import (
    AgentLog,
    Asset,
    Finding,
    FindingFeedback,
    RawMetadataItem,
    Run,
    RunStatus,
    Scope,
    TriageStatus,
    WebhookConfig,
    WebhookDelivery,
    WebhookDeliveryStatus,
)

# Canonical orderings for dashboard breakdowns (mirrors the report ordering).
_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]
_FINDING_TYPE_ORDER = ["gps", "email", "internal_path", "software_version", "debug_comment"]


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, run: Run) -> Run:
        self._session.add(run)
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def get(self, run_id: str) -> Run | None:
        return await self._session.get(Run, run_id)

    async def update(self, run: Run) -> Run:
        merged = await self._session.merge(run)
        await self._session.commit()
        await self._session.refresh(merged)
        return merged

    async def delete(self, run_id: str) -> bool:
        """Delete the run and every row that belongs to it (TASK-30)."""
        return await self.delete_cascade(run_id)

    async def delete_cascade(self, run_id: str) -> bool:
        """Delete one run in a single transaction, children first.

        Order: feedback, agent logs, raw metadata, findings, assets, webhook
        deliveries, derived knowledge-index rows, then the run. Explicit
        deletes, not ``ON DELETE CASCADE``, so SQLite and PostgreSQL behave
        the same with ``PRAGMA foreign_keys=ON``.
        """
        run = await self.get(run_id)
        if run is None:
            return False
        await self._session.exec(delete(FindingFeedback).where(FindingFeedback.run_id == run_id))
        await self._session.exec(delete(AgentLog).where(AgentLog.run_id == run_id))
        asset_ids = select(Asset.id).where(Asset.run_id == run_id)
        await self._session.exec(
            delete(RawMetadataItem).where(RawMetadataItem.asset_id.in_(asset_ids))  # type: ignore[attr-defined]
        )
        await self._session.exec(delete(Finding).where(Finding.run_id == run_id))
        await self._session.exec(delete(Asset).where(Asset.run_id == run_id))
        await self._session.exec(delete(WebhookDelivery).where(WebhookDelivery.run_id == run_id))
        await self._drop_knowledge_rows(run_id)
        await self._session.delete(run)
        await self._session.commit()
        return True

    async def _drop_knowledge_rows(self, run_id: str) -> None:
        """Drop derived index rows for this run when the index table exists."""
        dialect = self._session.get_bind().dialect.name
        if dialect == "sqlite":
            statement = "DELETE FROM knowledge_fts WHERE run_id = :run_id"
        elif dialect == "postgresql":
            statement = "DELETE FROM knowledge_vectors WHERE run_id = :run_id"
        else:
            return
        try:
            async with self._session.begin_nested():
                await self._session.exec(text(statement), params={"run_id": run_id})
        except Exception:
            # The index is derived and may not have been built yet.
            return

    async def list_terminal_started_before(self, moment: datetime) -> list[Run]:
        """Terminal runs whose ``started_at`` is strictly before ``moment``."""
        statement = select(Run).where(
            or_(
                Run.status == RunStatus.completed,
                Run.status == RunStatus.failed,
                Run.status == RunStatus.aborted,
            ),
            Run.started_at < moment,
        )
        result = await self._session.exec(statement)
        return list(result.all())

    async def list_all(self) -> list[Run]:
        result = await self._session.exec(select(Run))
        return list(result.all())

    async def list_recent(
        self,
        *,
        status: RunStatus | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> list[Run]:
        """Newest-first listing used by the v1.1 history surfaces.

        TASK-21 (v2.4): optional stable keyset pagination. ``cursor`` is a
        ``<started_at_iso>_<run_id>`` pair; when given, only runs strictly
        NEWER... (older, since we paginate newest-first) than the anchor are
        returned, so a run inserted between two pages never duplicates or
        drops a row. The composite ``(started_at DESC, id DESC)`` key is unique
        — the id break-tie keeps the ordering total — and is backed by
        ``ix_run_started_at_id`` (TASK-33). Fetch one row past ``limit``
        (``limit + 1``) so the caller
        can tell whether a next page exists without an extra count query.
        """
        statement = select(Run).order_by(
            Run.started_at.desc(), Run.id.desc()  # type: ignore[arg-type]
        )
        if status is not None:
            statement = statement.where(Run.status == status)
        if cursor is not None:
            started_at, run_id = _split_cursor(cursor)
            statement = statement.where(
                (Run.started_at < started_at)
                | ((Run.started_at == started_at) & (Run.id < run_id))
            )
        if limit is not None:
            # +1 probe: existence of a next page, not a count.
            statement = statement.limit(limit + 1)
        result = await self._session.exec(statement)
        return list(result.all())

    async def ids_with_scope(self, allowed_scope: str, *, exclude_id: str) -> list[str]:
        """Ids of other runs that share this exact scope snapshot."""
        result = await self._session.exec(
            select(Run.id).where(Run.allowed_scope == allowed_scope, Run.id != exclude_id)
        )
        return list(result.all())

    async def count(self, *, status: RunStatus | None = None) -> int:
        """Total rows under the given filter (TASK-21: untruncated "N runs")."""
        statement = select(func.count()).select_from(Run)
        if status is not None:
            statement = statement.where(Run.status == status)
        result = await self._session.exec(statement)
        return int(result.one())

    async def resolve(self, token: str) -> Run:
        """Full UUID or unique prefix (the 8-char stem ``list-runs`` shows)."""
        cleaned = token.strip()
        if not cleaned:
            raise RunNotFoundError(token)
        exact = await self.get(cleaned)
        if exact is not None:
            return exact
        result = await self._session.exec(select(Run))
        matches = [run for run in result.all() if run.id.startswith(cleaned)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AmbiguousRunError(cleaned, [run.id for run in matches])
        raise RunNotFoundError(token)

    async def list_open_started_before(self, moment: datetime) -> list[Run]:
        """Pending or running runs whose ``started_at`` is strictly before ``moment``.

        Used by startup recovery (TASK-28). A run this process created has a
        later ``started_at`` and is not returned.
        """
        statement = select(Run).where(
            or_(Run.status == RunStatus.pending, Run.status == RunStatus.running),
            Run.started_at < moment,
        )
        result = await self._session.exec(statement)
        return list(result.all())


class AssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, asset: Asset) -> Asset:
        self._session.add(asset)
        await self._session.commit()
        await self._session.refresh(asset)
        return asset

    async def get(self, asset_id: str) -> Asset | None:
        return await self._session.get(Asset, asset_id)

    async def update(self, asset: Asset) -> Asset:
        merged = await self._session.merge(asset)
        await self._session.commit()
        await self._session.refresh(merged)
        return merged

    async def delete(self, asset_id: str) -> bool:
        asset = await self.get(asset_id)
        if asset is None:
            return False
        await self._session.delete(asset)
        await self._session.commit()
        return True

    async def list_by_run(self, run_id: str) -> list[Asset]:
        result = await self._session.exec(select(Asset).where(Asset.run_id == run_id))
        return list(result.all())


class RawMetadataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, item: RawMetadataItem) -> RawMetadataItem:
        self._session.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def create_many(self, items: list[RawMetadataItem]) -> list[RawMetadataItem]:
        """Batch-insert the items of one asset in a single commit (TASK-01)."""
        self._session.add_all(items)
        await self._session.commit()
        return items

    async def get(self, item_id: int) -> RawMetadataItem | None:
        return await self._session.get(RawMetadataItem, item_id)

    async def delete(self, item_id: int) -> bool:
        item = await self.get(item_id)
        if item is None:
            return False
        await self._session.delete(item)
        await self._session.commit()
        return True

    async def list_by_asset(self, asset_id: str) -> list[RawMetadataItem]:
        result = await self._session.exec(
            select(RawMetadataItem).where(RawMetadataItem.asset_id == asset_id)
        )
        return list(result.all())

    async def list_by_run(self, run_id: str) -> list[RawMetadataItem]:
        result = await self._session.exec(
            select(RawMetadataItem)
            .join(Asset, RawMetadataItem.asset_id == Asset.id)
            .where(Asset.run_id == run_id)
        )
        return list(result.all())


class FindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, finding: Finding) -> Finding:
        self._session.add(finding)
        await self._session.commit()
        await self._session.refresh(finding)
        return finding

    async def create_many(self, findings: list[Finding]) -> list[Finding]:
        """Batch-insert the findings of one asset in a single commit (TASK-02)."""
        self._session.add_all(findings)
        await self._session.commit()
        return findings

    async def get(self, finding_id: str) -> Finding | None:
        return await self._session.get(Finding, finding_id)

    async def update(self, finding: Finding) -> Finding:
        merged = await self._session.merge(finding)
        await self._session.commit()
        await self._session.refresh(merged)
        return merged

    async def delete(self, finding_id: str) -> bool:
        finding = await self.get(finding_id)
        if finding is None:
            return False
        await self._session.delete(finding)
        await self._session.commit()
        return True

    async def list_by_run(self, run_id: str) -> list[Finding]:
        result = await self._session.exec(select(Finding).where(Finding.run_id == run_id))
        return list(result.all())

    async def set_triage(
        self,
        run_id: str,
        finding_id: str,
        *,
        status: TriageStatus,
        note: str | None,
        by: str,
    ) -> Finding | None:
        """Operator triage. Severity and evidence are never touched (TASK-35, rule 6)."""
        finding = await self._session.get(Finding, finding_id)
        if finding is None or finding.run_id != run_id:
            return None
        finding.triage_status = status
        finding.triage_note = note or None
        finding.triaged_by = by
        finding.triaged_at = datetime.now(UTC)
        self._session.add(finding)
        await self._session.commit()
        await self._session.refresh(finding)
        return finding

    async def with_asset_url(self, run_ids: list[str]) -> list[tuple[Finding, str]]:
        """Findings of many runs with their asset's final URL, in one join (TASK-35)."""
        if not run_ids:
            return []
        result = await self._session.exec(
            select(Finding, Asset.final_url)
            .join(Asset, Asset.id == Finding.asset_id)  # type: ignore[arg-type]
            .where(Finding.run_id.in_(run_ids))  # type: ignore[attr-defined]
            .order_by(Finding.created_at, Finding.id)  # type: ignore[arg-type]
        )
        return [(finding, url) for finding, url in result.all()]

    async def signatures_for_runs(self, run_ids: list[str]) -> set[str]:
        """Dedup signatures of many runs in one query (TASK-33)."""
        if not run_ids:
            return set()
        result = await self._session.exec(
            select(Finding.dedup_signature).where(Finding.run_id.in_(run_ids))  # type: ignore[attr-defined]
        )
        return set(result.all())

    async def list_by_asset(self, asset_id: str) -> list[Finding]:
        result = await self._session.exec(select(Finding).where(Finding.asset_id == asset_id))
        return list(result.all())


class AgentLogRepository:
    """Append-only audit log: no update — entries are never modified."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, entry: AgentLog) -> AgentLog:
        self._session.add(entry)
        await self._session.commit()
        await self._session.refresh(entry)
        return entry

    async def get(self, entry_id: str) -> AgentLog | None:
        return await self._session.get(AgentLog, entry_id)

    async def delete(self, entry_id: str) -> bool:
        entry = await self.get(entry_id)
        if entry is None:
            return False
        await self._session.delete(entry)
        await self._session.commit()
        return True

    async def list_by_run(self, run_id: str) -> list[AgentLog]:
        result = await self._session.exec(select(AgentLog).where(AgentLog.run_id == run_id))
        return list(result.all())


class ScopeRepository:
    """Persistent named scopes (TASK-10, v2.0). Persistence only, no validation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, scope: Scope) -> Scope:
        self._session.add(scope)
        await self._session.commit()
        await self._session.refresh(scope)
        return scope

    async def get(self, scope_id: str) -> Scope | None:
        return await self._session.get(Scope, scope_id)

    async def get_by_name(self, name: str) -> Scope | None:
        result = await self._session.exec(
            select(Scope).where(Scope.name.ilike(name.strip()))
        )
        return result.first()

    async def update(self, scope: Scope) -> Scope:
        merged = await self._session.merge(scope)
        await self._session.commit()
        await self._session.refresh(merged)
        return merged

    async def delete(self, scope_id: str) -> bool:
        scope = await self.get(scope_id)
        if scope is None:
            return False
        await self._session.delete(scope)
        await self._session.commit()
        return True

    async def list_all(self) -> list[Scope]:
        result = await self._session.exec(
            select(Scope).order_by(Scope.created_at.desc())  # type: ignore[arg-type]
        )
        return list(result.all())


class FeedbackRepository:
    """Operator feedback over findings (TASK-13, v2.1+). Persistence only.

    ``upsert_by_finding`` implements the "one active feedback per finding"
    contract: a new vote for a finding that already has feedback **replaces**
    the row instead of creating a duplicate, so the few-shot memory stays
    bounded and later examples win over earlier ones.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, feedback: FindingFeedback) -> FindingFeedback:
        self._session.add(feedback)
        await self._session.commit()
        await self._session.refresh(feedback)
        return feedback

    async def get_by_finding(self, finding_id: str) -> FindingFeedback | None:
        result = await self._session.exec(
            select(FindingFeedback).where(FindingFeedback.finding_id == finding_id)
        )
        return result.first()

    async def upsert_by_finding(self, feedback: FindingFeedback) -> FindingFeedback:
        """Insert, or replace the existing row for the same ``finding_id``.

        A replacement persists a brand-new row (fresh ``id``/``created_at``)
        and removes the previous one, so the few-shot memory always reflects
        the latest correction while the "one active feedback per finding"
        contract holds. The new row is returned.
        """
        existing = await self.get_by_finding(feedback.finding_id)
        if existing is not None:
            await self._session.delete(existing)
            # Flush so the DELETE is emitted before the INSERT of the new row;
            # without it SQLAlchemy may reorder and briefly hold both rows.
            await self._session.flush()
        self._session.add(feedback)
        await self._session.commit()
        await self._session.refresh(feedback)
        return feedback

    async def list_recent(self, limit: int = 50) -> list[FindingFeedback]:
        """Newest-first feedback rows, for the few-shot memory loader."""
        result = await self._session.exec(
            select(FindingFeedback).order_by(
                FindingFeedback.created_at.desc()  # type: ignore[arg-type]
            ).limit(limit)
        )
        return list(result.all())

    async def delete(self, finding_id: str) -> bool:
        feedback = await self.get_by_finding(finding_id)
        if feedback is None:
            return False
        await self._session.delete(feedback)
        await self._session.commit()
        return True


class DashboardRepository:
    """Read-only aggregations over runs/findings/assets/agent_log (TASK-11).

    Persistence layer only: fetches rows and counts them here so the service
    stays free of SQL. Every method opens exactly one query; no JOINs beyond
    the MVP volume, and **nothing writes**.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summary(self) -> dict[str, Any]:
        """Global counters via GROUP BY. The query count does not grow with rows."""
        status_rows = (
            await self._session.exec(select(Run.status, func.count(Run.id)).group_by(Run.status))
        ).all()
        by_status = {str(status): int(count) for status, count in status_rows}
        asset_rows = (
            await self._session.exec(
                select(Asset.extraction_status, func.count(Asset.id)).group_by(
                    Asset.extraction_status
                )
            )
        ).all()
        total_assets = sum(int(count) for _, count in asset_rows)
        assets_with_issues = sum(
            int(count) for status, count in asset_rows if str(status) != "ok"
        )
        # TASK-35: false positives are left out of every count and reported apart.
        kept = Finding.triage_status != TriageStatus.false_positive
        dismissed = int(
            (
                await self._session.exec(
                    select(func.count(Finding.id)).where(
                        Finding.triage_status == TriageStatus.false_positive
                    )
                )
            ).one()
        )
        severity_rows = (
            await self._session.exec(
                select(Finding.severity, func.count(Finding.id))
                .where(kept)
                .group_by(Finding.severity)
            )
        ).all()
        by_severity: dict[str, int] = {}
        unclassified = 0
        total_findings = 0
        for severity, count in severity_rows:
            total_findings += int(count)
            if severity is None:
                unclassified += int(count)
            else:
                by_severity[str(severity)] = int(count)
        type_rows = (
            await self._session.exec(
                select(Finding.finding_type, func.count(Finding.id))
                .where(kept)
                .group_by(Finding.finding_type)
            )
        ).all()
        by_type = {str(finding_type): int(count) for finding_type, count in type_rows}

        return {
            "total_runs": sum(by_status.values()),
            "by_status": by_status,
            "total_assets": total_assets,
            "assets_with_issues": assets_with_issues,
            "total_findings": total_findings,
            "by_severity": by_severity,
            "by_type": by_type,
            "unclassified": unclassified,
            "dismissed": dismissed,
        }

    async def severity_by_day(self, since: datetime) -> list[tuple[str, str | None, int]]:
        """``(YYYY-MM-DD, severity, count)`` of findings created since ``since`` (TASK-35)."""
        day = func.date(Finding.created_at)
        rows = (
            await self._session.exec(
                select(day, Finding.severity, func.count(Finding.id))
                .where(Finding.created_at >= since)
                .where(Finding.triage_status != TriageStatus.false_positive)
                .group_by(day, Finding.severity)
            )
        ).all()
        return [
            (str(date)[:10], None if severity is None else str(severity), int(count))
            for date, severity, count in rows
        ]

    async def top_domains(self, limit: int = 10) -> list[tuple[str, int]]:
        """Frequent domains across RFC titles + asset URLs, host-normalized."""
        counts: Counter[str] = Counter()

        for run in (await self._session.exec(select(Run))).all():
            try:
                scope = _json_list(run.allowed_scope)
            except (TypeError, ValueError):
                scope = []
            counts.update(normalize_host(entry) for entry in scope if normalize_host(entry))

        for asset in (await self._session.exec(select(Asset))).all():
            host = normalize_host(asset.final_url)
            if host:
                counts[host] += 1

        return counts.most_common(limit)

    async def top_evidence(self, limit: int = 10) -> list[dict[str, Any]]:
        """Frequent evidence snippets, grouped by dedup_signature in SQL."""
        rows = (
            await self._session.exec(
                select(
                    Finding.dedup_signature,
                    func.min(Finding.evidence_snippet),
                    func.min(Finding.finding_type),
                    func.count(Finding.id),
                )
                .where(Finding.triage_status != TriageStatus.false_positive)
                .group_by(Finding.dedup_signature)
                .order_by(func.count(Finding.id).desc(), func.min(Finding.evidence_snippet))
                .limit(limit)
            )
        ).all()
        return [
            {
                "signature": signature,
                "evidence_snippet": snippet,
                "finding_type": str(finding_type),
                "occurrences": int(occurrences),
            }
            for signature, snippet, finding_type, occurrences in rows
        ]

    async def agent_usage(self) -> dict[str, int]:
        """Total LLM usage from agent_log (all zeros when the agents never ran)."""
        logs = list((await self._session.exec(select(AgentLog))).all())
        return {
            "calls": len(logs),
            "prompt_tokens": sum(log.prompt_tokens for log in logs),
            "completion_tokens": sum(log.completion_tokens for log in logs),
            "total_tokens": sum(
                (log.prompt_tokens or 0) + (log.completion_tokens or 0) for log in logs
            ),
            "latency_ms": sum(log.latency_ms for log in logs),
        }


class WebhookConfigRepository:
    """Persistent webhook configurations (TASK-15, v2.2). Persistence only."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, config: WebhookConfig) -> WebhookConfig:
        self._session.add(config)
        await self._session.commit()
        await self._session.refresh(config)
        return config

    async def get(self, webhook_id: str) -> WebhookConfig | None:
        return await self._session.get(WebhookConfig, webhook_id)

    async def update(self, config: WebhookConfig) -> WebhookConfig:
        merged = await self._session.merge(config)
        await self._session.commit()
        await self._session.refresh(merged)
        return merged

    async def delete(self, webhook_id: str) -> bool:
        """Delete the config and its delivery rows in one transaction (FKs are enforced)."""
        config = await self.get(webhook_id)
        if config is None:
            return False
        await self._session.exec(
            delete(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id)
        )
        await self._session.delete(config)
        await self._session.commit()
        return True

    async def list_all(self) -> list[WebhookConfig]:
        result = await self._session.exec(
            select(WebhookConfig).order_by(  # type: ignore[arg-type]
                WebhookConfig.created_at.desc()
            )
        )
        return list(result.all())

    async def list_active_by_event(self, event: RunStatus) -> list[WebhookConfig]:
        """Active webhooks subscribed to one terminal event, for the dispatcher."""
        result = await self._session.exec(
            select(WebhookConfig).where(
                WebhookConfig.active.is_(True),
                WebhookConfig.event == event,
            )
        )
        return list(result.all())


class WebhookDeliveryRepository:
    """Persisted relay-buffer rows of outbound webhook deliveries (TASK-15)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, delivery: WebhookDelivery) -> WebhookDelivery:
        self._session.add(delivery)
        await self._session.commit()
        await self._session.refresh(delivery)
        return delivery

    async def get(self, delivery_id: str) -> WebhookDelivery | None:
        return await self._session.get(WebhookDelivery, delivery_id)

    async def update(self, delivery: WebhookDelivery) -> WebhookDelivery:
        merged = await self._session.merge(delivery)
        await self._session.commit()
        await self._session.refresh(merged)
        return merged

    async def delete(self, delivery_id: str) -> bool:
        delivery = await self.get(delivery_id)
        if delivery is None:
            return False
        await self._session.delete(delivery)
        await self._session.commit()
        return True

    async def get_by_webhook_run(self, webhook_id: str, run_id: str) -> WebhookDelivery | None:
        """The (unique) delivery row for one webhook/run pair, or None."""
        result = await self._session.exec(
            select(WebhookDelivery).where(
                WebhookDelivery.webhook_id == webhook_id,
                WebhookDelivery.run_id == run_id,
            )
        )
        return result.first()

    async def list_by_webhook(self, webhook_id: str) -> list[WebhookDelivery]:
        result = await self._session.exec(
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == webhook_id)
            .order_by(WebhookDelivery.created_at.desc())  # type: ignore[arg-type]
        )
        return list(result.all())

    async def list_pending(self, limit: int = 50) -> list[WebhookDelivery]:
        """Retriable deliveries whose next attempt is due, oldest first.

        Used by the dispatcher's sweep on startup so relay-buffer rows
        survive a restart (the idempotency key makes replays safe).
        """
        import time

        now = time.time()
        result = await self._session.exec(
            select(WebhookDelivery)
            .where(WebhookDelivery.status == WebhookDeliveryStatus.pending)
            .where(WebhookDelivery.next_retry_at.is_(None) | (WebhookDelivery.next_retry_at <= now))
            .order_by(WebhookDelivery.created_at.asc())  # type: ignore[arg-type]
            .limit(limit)
        )
        return list(result.all())


def _json_list(payload: str) -> list[str]:
    """Decode a JSON list-of-strings column used by top_domains."""
    parsed = json.loads(payload)
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item)]
    if isinstance(parsed, str):
        return [parsed]
    return []


def _split_cursor(cursor: str) -> tuple[datetime, str]:
    """Parse a ``<started_at_iso>_<run_id>`` keyset anchor.

    ``started_at`` arrives as ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (the shape
    ``_encode_cursor`` emits — a ``Z`` instead of ``+00:00`` so the ``+``
    cannot be mis-decoded as a space inside a query string). A legacy
    ``+00:00`` form is also accepted. The delimiter is the FIRST underscore
    after the ``T`` so a UUID run_id (hyphens only) can never collide with
    the split. A malformed cursor results in a 422 handled by the API layer,
    not here.
    """
    try:
        separator = cursor.index("_")
        raw_started_at = cursor[:separator]
        run_id = cursor[separator + 1 :]
        # Normalize the trailing Z to +00:00 so fromisoformat parses it.
        if raw_started_at.endswith("Z"):
            raw_started_at = raw_started_at[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw_started_at)
        started_at = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        raise ValueError(f"invalid cursor: {cursor}") from None
    if not run_id:
        raise ValueError(f"invalid cursor: {cursor}")
    return started_at, run_id
