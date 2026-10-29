"""Investigation groups (Fase 3).

Grouping is not tenancy: every reader of the install can list every
investigation. Attaching a run does not change its scope, its findings or
its triage. Suggestions are computed when findings are listed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError

from metatracer.core.exceptions import InvestigationConflictError, MetaTracerError
from metatracer.db.models import Investigation, InvestigationStatus, Run
from metatracer.db.repositories import InvestigationRepository
from metatracer.services.investigation import attach_run, create_investigation, detach_run

router = APIRouter(prefix="/api/investigations", tags=["investigations"])

_MAX_NAME = 80
_MAX_DESCRIPTION = 2000


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class InvestigationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=_MAX_NAME)
    description: str | None = Field(default=None, max_length=_MAX_DESCRIPTION)


class InvestigationUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=_MAX_NAME)
    description: str | None = Field(default=None, max_length=_MAX_DESCRIPTION)
    status: InvestigationStatus


class InvestigationRunResponse(BaseModel):
    run_id: str
    run_ref: str | None
    status: str
    target: str
    started_at: datetime


class InvestigationResponse(BaseModel):
    id: str
    name: str
    description: str | None
    status: InvestigationStatus
    created_at: datetime
    run_count: int
    runs: list[InvestigationRunResponse] = Field(default_factory=list)

    @classmethod
    def from_model(
        cls,
        investigation: Investigation,
        *,
        run_count: int,
        runs: list[Run] | None = None,
    ) -> InvestigationResponse:
        return cls(
            id=investigation.id,
            name=investigation.name,
            description=investigation.description,
            status=InvestigationStatus(investigation.status),
            created_at=_as_utc(investigation.created_at),
            run_count=run_count,
            runs=[_run_response(run) for run in runs or []],
        )


class InvestigationListResponse(BaseModel):
    total: int
    investigations: list[InvestigationResponse]


class AttachRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)


def _run_response(run: Run) -> InvestigationRunResponse:
    targets = _json_str_list(run.target_input)
    return InvestigationRunResponse(
        run_id=run.id,
        run_ref=run.run_ref,
        status=str(run.status.value if hasattr(run.status, "value") else run.status),
        target=targets[0] if targets else "",
        started_at=_as_utc(run.started_at),
    )


def _json_str_list(payload: str) -> list[str]:
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    return []


def _conflict(exc: InvestigationConflictError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


def _missing(exc: MetaTracerError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("")
async def list_investigations(request: Request) -> InvestigationListResponse:
    async with request.app.state.session_factory() as session:
        rows = await InvestigationRepository(session).list_recent()
        counts = await InvestigationRepository(session).run_counts()
    items = [
        InvestigationResponse.from_model(row, run_count=counts.get(row.id, 0)) for row in rows
    ]
    return InvestigationListResponse(total=len(items), investigations=items)


@router.post("", status_code=201)
async def create(body: InvestigationCreate, request: Request) -> InvestigationResponse:
    async with request.app.state.session_factory() as session:
        try:
            created = await create_investigation(
                session, name=body.name, description=body.description
            )
        except InvestigationConflictError as exc:
            raise _conflict(exc) from exc
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409, detail="an investigation with that name already exists"
            ) from exc
    return InvestigationResponse.from_model(created, run_count=0)


@router.get("/{investigation_id}")
async def get_investigation(investigation_id: str, request: Request) -> InvestigationResponse:
    async with request.app.state.session_factory() as session:
        row = await InvestigationRepository(session).get(investigation_id)
        if row is None:
            raise HTTPException(status_code=404, detail="investigation not found")
        runs = await InvestigationRepository(session).runs_for(investigation_id)
    return InvestigationResponse.from_model(row, run_count=len(runs), runs=runs)


@router.put("/{investigation_id}")
async def update_investigation(
    investigation_id: str, body: InvestigationUpdate, request: Request
) -> InvestigationResponse:
    async with request.app.state.session_factory() as session:
        repo = InvestigationRepository(session)
        row = await repo.get(investigation_id)
        if row is None:
            raise HTTPException(status_code=404, detail="investigation not found")
        taken = await repo.get_by_name(body.name)
        if taken is not None and taken.id != row.id:
            raise HTTPException(
                status_code=409, detail=f"an investigation named {body.name!r} already exists"
            )
        row.name = body.name
        row.description = body.description
        row.status = body.status
        try:
            saved = await repo.update(row)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409, detail="an investigation with that name already exists"
            ) from exc
        runs = await repo.runs_for(investigation_id)
    return InvestigationResponse.from_model(saved, run_count=len(runs), runs=runs)


@router.post("/{investigation_id}/runs")
async def attach(
    investigation_id: str, body: AttachRunRequest, request: Request
) -> InvestigationResponse:
    async with request.app.state.session_factory() as session:
        try:
            await attach_run(session, investigation_id, body.run_id)
        except InvestigationConflictError as exc:
            raise _conflict(exc) from exc
        except MetaTracerError as exc:
            raise _missing(exc) from exc
        row = await InvestigationRepository(session).get(investigation_id)
        runs = await InvestigationRepository(session).runs_for(investigation_id)
    if row is None:  # pragma: no cover - attach just found it
        raise HTTPException(status_code=404, detail="investigation not found")
    return InvestigationResponse.from_model(row, run_count=len(runs), runs=runs)


@router.delete("/{investigation_id}/runs/{run_id}", status_code=204)
async def detach(investigation_id: str, run_id: str, request: Request) -> None:
    async with request.app.state.session_factory() as session:
        try:
            await detach_run(session, investigation_id, run_id)
        except MetaTracerError as exc:
            raise _missing(exc) from exc
