"""REST endpoints for persistent scopes (TASK-10, v2.0).

Storage only: normalization and wildcard matching stay in ``ScopeValidator``;
this router persists a named, reusable set of authorized domains. Deleting or
editing a Scope never alters persisted runs — a scan copies the resolved
``domains`` onto ``Run.allowed_scope`` (TASK-10, subtask 10.4).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from metatracer.core.safety.scope import normalize_host
from metatracer.db.models import Scope
from metatracer.db.repositories import ScopeRepository

router = APIRouter(prefix="/api/scopes", tags=["scopes"])

_MAX_NAME_CHARS = 64


def _now_utc() -> datetime:
    """Timezone-aware UTC timestamps, matching the models' `_utc_now`."""
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; every write is UTC (see db/models.py)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ScopeData(BaseModel):
    """Shared fields for create/update/response payloads."""

    name: str = Field(min_length=1, max_length=_MAX_NAME_CHARS)
    description: str | None = Field(default=None, max_length=1000)
    domains: list[str] = Field(min_length=1)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("domains")
    @classmethod
    def _normalize_domains(cls, values: list[str]) -> list[str]:
        """Host-normalize every entry and drop ones that normalize to empty.

        Matching itself stays in ``ScopeValidator`` at scan time; here we only
        keep the same normalization so what is stored matches what is matched.
        """
        cleaned: list[str] = []
        for value in values:
            host = normalize_host(value)
            if host:
                cleaned.append(host)
        return cleaned


class ScopeCreate(ScopeData):
    """POST /api/scopes body."""


class ScopeUpdate(ScopeData):
    """PUT /api/scopes/{scope_id} body (full replacement, no PATCH)."""


class ScopeResponse(BaseModel):
    """One persisted scope, with the domains actually stored (normalized)."""

    id: str
    name: str
    description: str | None
    domains: list[str]
    total_domains: int
    created_at: datetime

    @classmethod
    def from_scope(cls, scope: Scope) -> ScopeResponse:
        return cls(
            id=scope.id,
            name=scope.name,
            description=scope.description,
            domains=_json_str_list(scope.domains),
            total_domains=len(_json_str_list(scope.domains)),
            created_at=_as_utc(scope.created_at),
        )


class ScopeListResponse(BaseModel):
    """GET /api/scopes: newest first."""

    total: int
    scopes: list[ScopeResponse]


def _json_str_list(payload: str) -> list[str]:
    """Decode a JSON list-of-strings column; corrupt input degrades to []."""
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return [payload.strip()] if payload.strip() else []
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(parsed, str) and parsed.strip():
        return [parsed.strip()]
    return []


@router.post("", status_code=201, response_model=ScopeResponse)
async def create_scope(payload: ScopeCreate, request: Request) -> ScopeResponse:
    """Create a scope; ``name`` must be unique case-insensitively (409)."""
    async with request.app.state.session_factory() as session:
        repo = ScopeRepository(session)
        if await repo.get_by_name(payload.name) is not None:
            raise HTTPException(status_code=409, detail="a scope with this name already exists")
        scope = await repo.create(
            Scope(
                name=payload.name,
                description=payload.description,
                domains=json.dumps(payload.domains),
            )
        )
    return ScopeResponse.from_scope(scope)


@router.get("", response_model=ScopeListResponse)
async def list_scopes(request: Request) -> ScopeListResponse:
    """List persisted scopes, newest first (TASK-08-style local data)."""
    async with request.app.state.session_factory() as session:
        scopes = await ScopeRepository(session).list_all()
    return ScopeListResponse(
        total=len(scopes), scopes=[ScopeResponse.from_scope(s) for s in scopes]
    )


@router.get("/{scope_id}", response_model=ScopeResponse)
async def get_scope(scope_id: str, request: Request) -> ScopeResponse:
    """Detail of one scope."""
    async with request.app.state.session_factory() as session:
        scope = await ScopeRepository(session).get(scope_id)
    if scope is None:
        raise HTTPException(status_code=404, detail="scope not found")
    return ScopeResponse.from_scope(scope)


@router.put("/{scope_id}", response_model=ScopeResponse)
async def update_scope(scope_id: str, payload: ScopeUpdate, request: Request) -> ScopeResponse:
    """Full replacement (no PATCH); the same name-uniqueness rule applies."""
    async with request.app.state.session_factory() as session:
        repo = ScopeRepository(session)
        scope = await repo.get(scope_id)
        if scope is None:
            raise HTTPException(status_code=404, detail="scope not found")
        existing = await repo.get_by_name(payload.name)
        if existing is not None and existing.id != scope_id:
            raise HTTPException(status_code=409, detail="a scope with this name already exists")
        scope.name = payload.name
        scope.description = payload.description
        scope.domains = json.dumps(payload.domains)
        updated = await repo.update(scope)
    return ScopeResponse.from_scope(updated)


@router.delete("/{scope_id}", status_code=204)
async def delete_scope(scope_id: str, request: Request) -> Response:
    """Delete a scope; persisted runs keep their own copied scope."""
    async with request.app.state.session_factory() as session:
        deleted = await ScopeRepository(session).delete(scope_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="scope not found")
    return Response(status_code=204)