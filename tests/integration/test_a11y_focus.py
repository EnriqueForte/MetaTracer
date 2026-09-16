"""Accessibility affordances of the Web UI (TASK-20, 20.4).

Static assertions over the rendered HTML shells: the shared layout carries a
skip-link and ARIA attributes; the scan wizard ships a modal dialog with
focus management and Escape handling; the run page ships a finding drawer with
role/aria-modal and keyboard-activatable rows. No new dependencies (no
axe-core): these lock the structural a11y contract.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from metatracer.api.app import create_app
from metatracer.core.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/a11y-test.db",
        rate_limit_rps=1000.0,
        llm_api_key="",
        llm_base_url="",
        llm_model="",
    )


@pytest.fixture()
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    app = create_app(_settings(tmp_path), reports_dir=tmp_path / "reports")
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture()
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def test_shared_layout_has_skip_link_and_nav(client) -> None:
    """Every page shares base.html: a skip-to-content link and a labeled nav."""
    for path in ["/", "/runs", "/dashboard", "/scopes"]:
        response = await client.get(path)
        html = response.text
        assert "Skip to main content" in html
        assert 'id="main-content"' in html
        assert 'aria-label="Primary"' in html


async def test_scope_modal_is_accessible_dialog(client) -> None:
    """The scan wizard's scope-confirmation modal is an accessible dialog."""
    response = await client.get("/")
    html = response.text
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-labelledby="scope-modal-title"' in html
    # Focus is moved into the dialog on open (20.3).
    assert "scope-modal-cancel" in html
    assert "lastFocused" in html
    # Escape closes the modal.
    assert "@keydown.escape.window" in html


async def test_finding_drawer_is_accessible_dialog(client) -> None:
    """The run page's finding drawer is an accessible, focus-trapping dialog."""
    response = await client.get("/runs/00000000-0000-4000-8000-000000000000")
    html = response.text
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-labelledby="finding-drawer-title"' in html
    assert "drawerClose" in html  # close button ref for focus entry
    assert "trapFocus" in html  # Tab trapping helper


async def test_finding_rows_are_keyboard_activatable(client) -> None:
    """Findings rows open the drawer on Enter, not only on click (20.3)."""
    response = await client.get("/runs/00000000-0000-4000-8000-000000000000")
    html = response.text
    assert "@keydown.enter=\"select(finding)\"" in html
    assert 'tabindex="0"' in html


async def test_notifications_bell_has_expanded_controls(client) -> None:
    """The notification bell announces its state and controls its panel."""
    for path in ["/", "/runs", "/dashboard", "/scopes"]:
        response = await client.get(path)
        html = response.text
        assert 'aria-expanded' in html
        assert 'aria-controls="notifications-panel"' in html
        assert 'aria-haspopup="true"' in html
