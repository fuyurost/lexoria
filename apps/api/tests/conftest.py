"""Shared fixtures. PG-backed integration tests run only when
TEST_DATABASE_URL is set (e.g. postgresql+psycopg://user:pass@127.0.0.1:5432/
lexoria_test); unit tests never need a database.
"""
import os

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if TEST_DATABASE_URL:
    # The app reads DATABASE_URL once at import time; point it at the test DB
    # before any app module is imported (conftest loads before test modules).
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402


@pytest.fixture()
def client():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL 未设置，跳过数据库集成测试")
    from sqlalchemy import create_engine

    from app.db.base import Base

    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(engine)
    engine.dispose()
