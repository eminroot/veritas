"""The real app serves the assistant at /v1/assistant; tests/api/test_assistant.py has the rest."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veritas.assistant.config import AssistantSettings
from veritas.assistant.service import Assistant


def test_the_app_serves_the_assistant(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    off = Assistant(AssistantSettings(_env_file=None, openai_api_key=None), signing_key=b"k" * 32)
    monkeypatch.setattr(app.state, "assistant", off, raising=False)
    assert client.get("/v1/assistant").json() == {"available": False}
    res = client.post("/v1/assistant/messages", json={"message": "Where does my money go?"})
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "assistant_unavailable"
