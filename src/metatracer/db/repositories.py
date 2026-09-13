"""CRUD repositories: persistence only — no business logic in this layer."""

import json
from collections import Counter
from typing import Any

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
        run = await self.get(run_id)
        if run is None:
            return False
        await self._session.delete(run)
        await self._session.commit()
        return True

    async def list_all(self) -> list[Run]:
        result = await self._session.exec(select(Run))
        return list(result.all())

    async def list_recent(
        self, *, status: RunStatus | None = None, limit: int | None = None
    ) -> list[Run]:
        """Newest-first listing used by the v1.1 history surfaces."""
        statement = select(Run).order_by(Run.started_at.desc())  # type: ignore[arg-type]
        if status is not None:
            statement = statement.where(Run.status == status)
        if limit is not None:
            statement = statement.limit(limit)
        result = await self._session.exec(statement)
        return list(result.all())

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
        """Global counters: runs by status, assets, findings, breakdowns."""
        runs = list((await self._session.exec(select(Run))).all())
        findings = list((await self._session.exec(select(Finding))).all())
        assets = list((await self._session.exec(select(Asset))).all())

        by_status = Counter(str(run.status) for run in runs)
        severities = [str(finding.severity) for finding in findings if finding.severity]
        by_severity = Counter(severities)
        by_type = Counter(str(finding.finding_type) for finding in findings)
        unclassified = sum(1 for finding in findings if finding.severity is None)

        return {
            "total_runs": len(runs),
            "by_status": by_status,
            "total_assets": len(assets),
            "assets_with_issues": sum(
                1 for asset in assets if str(asset.extraction_status) != "ok"
            ),
            "total_findings": len(findings),
            "by_severity": by_severity,
            "by_type": by_type,
            "unclassified": unclassified,
        }

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
        """Frequent evidence snippets, grouped by dedup_signature (first wins)."""
        findings = list((await self._session.exec(select(Finding))).all())
        by_signature: dict[str, Finding] = {}
        for finding in findings:
            if finding.dedup_signature not in by_signature:
                by_signature[finding.dedup_signature] = finding

        def _occurrences(finding: Finding) -> int:
            return sum(1 for x in findings if x.dedup_signature == finding.dedup_signature)

        ranked = sorted(
            by_signature.values(),
            key=lambda f: (-_occurrences(f), f.evidence_snippet),
        )
        return [
            {
                "signature": finding.dedup_signature,
                "evidence_snippet": finding.evidence_snippet,
                "finding_type": str(finding.finding_type),
                "occurrences": _occurrences(finding),
            }
            for finding in ranked[:limit]
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
        config = await self.get(webhook_id)
        if config is None:
            return False
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
