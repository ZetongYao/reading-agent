from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def app_settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data",
        app_env="test",
        test_translation="测试释义",
    )


@pytest.fixture
def client(app_settings) -> Iterator[TestClient]:
    with TestClient(create_app(app_settings)) as test_client:
        yield test_client

