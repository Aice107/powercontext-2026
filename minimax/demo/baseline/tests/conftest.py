from __future__ import annotations

import pytest

from app.api import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app(tmp_path / "taskhub-test.sqlite3")


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_path(app):
    return app.config["DB_PATH"]
