"""Packaged Alembic migrations for the PostgreSQL backend (TASK-23, Eje B).

The directory is a regular package only so ``setuptools`` ships the migration
scripts inside the wheel; Alembic discovers versions by file scanning, so the
``__init__.py`` files are never imported by the migration runner itself.
"""
