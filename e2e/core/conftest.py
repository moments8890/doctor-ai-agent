"""
核心端到端冒烟测试的 DB fixture 复用配置。

Reuse unit-test DB fixtures for core E2E smoke tests.
"""

from tests.conftest import db_session, session_factory  # noqa: F401
