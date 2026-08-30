import importlib
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database.db as db


@pytest.fixture
def app(monkeypatch):
    fd, path = tempfile.mkstemp()
    os.close(fd)
    monkeypatch.setattr(db, "DB_PATH", path)

    if "app" in sys.modules:
        flask_app_module = importlib.reload(sys.modules["app"])
    else:
        flask_app_module = importlib.import_module("app")

    flask_app_module.app.config["TESTING"] = True

    yield flask_app_module.app

    os.remove(path)


@pytest.fixture
def client(app):
    return app.test_client()
