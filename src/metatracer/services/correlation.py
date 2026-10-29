"""Persist and read shared-value groups (Fase 3).

Writing happens at the end of detection, from observations the correlator
already accepted. Reading never invents a link: a group is returned only when
at least two assets carry the value, and the notice says that is not identity.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from metatracer.db.models import Asset, AssetValue, CorrelationKind, ValueEntity
from metatracer.detectors.correlate import ValueObservation

NOTICE = "Shared value across {count} assets — not proof of common identity."
_MEMBER_CAP = 25


@dataclass(frozen=True, slots=True)
class CorrelationMember:
    asset_id: str
    asset_url: str
    run_id: str
    namespace: str
    key: str


@dataclass(frozen=True, slots=True)
class CorrelationGroup:
    kind: CorrelationKind
    value_norm: str
    occurrences: int
    first_seen_run_id: str
    notice: str
    members: tuple[CorrelationMember, ...]
    members_truncated: bool


async def record_observations(
    session: AsyncSession, run_id: str, asset_id: str, observations: list[ValueObservation]
) -> None:
    """Link this asset to each value. Re-running detection does not duplicate rows."""
    for observation in observations:
        entity = await _entity(session, run_id, observation)
        await _link(session, asset_id, entity.id, observation.namespace, observation.key)
        entity.occurrences = await _asset_count(session, entity.id)
        session.add(entity)
        await session.commit()


async def groups_touching_run(session: AsyncSession, run_id: str) -> list[CorrelationGroup]:
    """Groups with 2+ assets that include at least one asset of this run."""
    entity_ids = await session.exec(
        select(AssetValue.entity_id)
        .join(Asset, Asset.id == AssetValue.asset_id)  # type: ignore[arg-type]
        .where(Asset.run_id == run_id)
        .distinct()
    )
    groups: list[CorrelationGroup] = []
    for entity_id in entity_ids.all():
        entity = await session.get(ValueEntity, entity_id)
        if entity is None or entity.occurrences < 2:
            continue
        members = await _members(session, entity.id)
        shown = members[:_MEMBER_CAP]
        groups.append(
            CorrelationGroup(
                kind=CorrelationKind(entity.kind),
                value_norm=entity.value_norm,
                occurrences=entity.occurrences,
                first_seen_run_id=entity.first_seen_run_id,
                notice=NOTICE.format(count=entity.occurrences),
                members=tuple(shown),
                members_truncated=len(members) > _MEMBER_CAP,
            )
        )
    groups.sort(key=lambda group: (-group.occurrences, group.kind.value, group.value_norm))
    return groups


async def _entity(session: AsyncSession, run_id: str, observation: ValueObservation) -> ValueEntity:
    result = await session.exec(
        select(ValueEntity).where(
            ValueEntity.kind == observation.kind,
            ValueEntity.value_hash == observation.value_hash,
        )
    )
    found = result.first()
    if found is not None:
        return found
    created = ValueEntity(
        kind=observation.kind,
        value_hash=observation.value_hash,
        value_norm=observation.value_norm,
        first_seen_run_id=run_id,
        occurrences=0,
    )
    session.add(created)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        again = await session.exec(
            select(ValueEntity).where(
                ValueEntity.kind == observation.kind,
                ValueEntity.value_hash == observation.value_hash,
            )
        )
        raced = again.first()
        if raced is None:  # pragma: no cover - the conflicting row exists
            raise
        return raced
    await session.refresh(created)
    return created


async def _link(
    session: AsyncSession, asset_id: str, entity_id: str, namespace: str, key: str
) -> None:
    result = await session.exec(
        select(AssetValue).where(
            AssetValue.asset_id == asset_id,
            AssetValue.entity_id == entity_id,
            AssetValue.namespace == namespace,
            AssetValue.key == key,
        )
    )
    if result.first() is not None:
        return
    session.add(AssetValue(asset_id=asset_id, entity_id=entity_id, namespace=namespace, key=key))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()


async def _asset_count(session: AsyncSession, entity_id: str) -> int:
    result = await session.exec(
        select(func.count(func.distinct(AssetValue.asset_id))).where(
            AssetValue.entity_id == entity_id
        )
    )
    return int(result.one())


async def _members(session: AsyncSession, entity_id: str) -> list[CorrelationMember]:
    result = await session.exec(
        select(AssetValue, Asset)
        .join(Asset, Asset.id == AssetValue.asset_id)  # type: ignore[arg-type]
        .where(AssetValue.entity_id == entity_id)
        .order_by(Asset.discovered_at, Asset.id)  # type: ignore[arg-type]
    )
    return [
        CorrelationMember(
            asset_id=asset.id,
            asset_url=asset.final_url,
            run_id=asset.run_id,
            namespace=link.namespace,
            key=link.key,
        )
        for link, asset in result.all()
    ]
