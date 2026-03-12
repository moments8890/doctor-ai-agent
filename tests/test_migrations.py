"""Alembic migration unit tests for schema repair scripts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Optional
from unittest.mock import patch


class _FakeBatchOp:
    def __init__(self) -> None:
        self.calls = []

    def __enter__(self) -> "_FakeBatchOp":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def drop_constraint(self, name: str, type_: str) -> None:
        self.calls.append(("drop_constraint", name, type_))

    def create_check_constraint(self, name: str, sqltext: str) -> None:
        self.calls.append(("create_check_constraint", name, sqltext))


class _FakeOp:
    def __init__(self) -> None:
        self.batch_args = None
        self.batch = _FakeBatchOp()

    def batch_alter_table(self, table_name: str, recreate: Optional[str] = None) -> _FakeBatchOp:
        self.batch_args = (table_name, recreate)
        return self.batch


def _load_migration_module(module_name: str, filename: str):
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0004_upgrade_replaces_doctor_task_type_constraint():
    module = _load_migration_module("migration_0004_upgrade", "0004_expand_doctor_task_types.py")
    fake_op = _FakeOp()

    with patch.object(module, "op", fake_op):
        module.upgrade()

    assert fake_op.batch_args == ("doctor_tasks", "always")
    assert ("drop_constraint", "ck_doctor_tasks_task_type", "check") in fake_op.batch.calls
    assert (
        "create_check_constraint",
        "ck_doctor_tasks_task_type",
        "task_type IN ('follow_up','emergency','appointment','general',"
        "'lab_review','referral','imaging','medication')",
    ) in fake_op.batch.calls


def test_0004_downgrade_restores_legacy_doctor_task_type_constraint():
    module = _load_migration_module("migration_0004_downgrade", "0004_expand_doctor_task_types.py")
    fake_op = _FakeOp()

    with patch.object(module, "op", fake_op):
        module.downgrade()

    assert fake_op.batch_args == ("doctor_tasks", "always")
    assert ("drop_constraint", "ck_doctor_tasks_task_type", "check") in fake_op.batch.calls
    assert (
        "create_check_constraint",
        "ck_doctor_tasks_task_type",
        "task_type IN ('follow_up','emergency','appointment')",
    ) in fake_op.batch.calls
