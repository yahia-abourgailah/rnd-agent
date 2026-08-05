"""Chat endpoint contract, with the graph stubbed so no model or database is needed."""

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from api.main import app
from api.security import require_api_key
from config.settings import settings


class RecordingGraph:
    """Captures the config it was invoked with, so thread routing is assertable."""

    def __init__(self):
        self.configs = []

    def invoke(self, state, config=None):
        self.configs.append(config)
        return {"messages": [AIMessage(content="42 launches.")]}


@pytest.fixture
def graph():
    recorder = RecordingGraph()
    app.state.chat_graph = recorder
    app.dependency_overrides[require_api_key] = lambda: None
    yield recorder
    app.dependency_overrides.clear()
    app.state.chat_graph = None


@pytest.fixture
def client(graph):
    return TestClient(app)


def test_chat_returns_the_models_answer(client):
    response = client.post("/chat", json={"message": "how many launches?"})

    assert response.status_code == 200
    assert response.json()["reply"] == "42 launches."


def test_a_new_conversation_gets_an_id_the_caller_can_reuse(client):
    body = client.post("/chat", json={"message": "hi"}).json()

    assert body["conversation_id"]


def test_follow_ups_reuse_the_callers_conversation_id(client, graph):
    """The bug this guards: a fresh uuid per request meant the checkpointer
    never saw a second turn, so 'memory' persisted nothing usable."""
    first = client.post("/chat", json={"message": "how many in New Cairo?"}).json()

    client.post(
        "/chat",
        json={"message": "and in Sheikh Zayed?", "conversation_id": first["conversation_id"]},
    )

    thread_ids = [c["configurable"]["thread_id"] for c in graph.configs]
    assert thread_ids[0] == thread_ids[1] == first["conversation_id"]


def test_separate_conversations_do_not_share_a_thread(client, graph):
    client.post("/chat", json={"message": "one"})
    client.post("/chat", json={"message": "two"})

    thread_ids = {c["configurable"]["thread_id"] for c in graph.configs}
    assert len(thread_ids) == 2


def test_chat_requires_the_api_key(monkeypatch):
    """Every other data route is behind the key; a route that runs SQL must not
    be the one exception."""
    monkeypatch.setattr(settings, "api_key", "secret", raising=False)
    app.state.chat_graph = RecordingGraph()
    app.dependency_overrides.clear()

    unauthenticated = TestClient(app).post("/chat", json={"message": "hi"})
    authenticated = TestClient(app).post(
        "/chat", json={"message": "hi"}, headers={"X-API-Key": "secret"}
    )

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200


def test_chat_reports_unavailable_when_the_agent_failed_to_start(client):
    app.state.chat_graph = None

    response = client.post("/chat", json={"message": "hi"})

    assert response.status_code == 503


def test_empty_messages_are_rejected_before_reaching_the_model(client, graph):
    response = client.post("/chat", json={"message": "   "})

    assert response.status_code == 422 or graph.configs == []
