"""The tool loop is the part that was missing: bound tools with no ToolNode
meant the graph ended on the tool-call message and never ran any SQL."""

from langchain_core.messages import AIMessage, HumanMessage

from chatbot_agent.graph import build_graph


class FakeModel:
    """Stands in for the chat model: emits a tool call on the first turn, then a
    plain answer. Keeps the test offline — no endpoint, no database."""

    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "query_database",
                        "args": {"query": "SELECT count(*) FROM launches"},
                        "id": "call-1",
                    }
                ],
            )
        return AIMessage(content="There are 42 launches.")


def test_graph_executes_tool_calls_and_feeds_results_back(monkeypatch):
    fake_model = FakeModel()
    monkeypatch.setattr("chatbot_agent.nodes.chatbot.get_llm_with_tools", lambda: fake_model)
    monkeypatch.setattr(
        "chatbot_agent.tools.postgres.run_read_only_query",
        lambda sql, max_rows=None: [(42,)],
    )

    result = build_graph().invoke({"messages": [HumanMessage(content="how many launches?")]})

    messages = result["messages"]
    # human -> tool call -> tool result -> answer: the tool result existing at
    # all is what proves the loop is wired.
    assert [type(m).__name__ for m in messages] == [
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
        "AIMessage",
    ]
    assert "42" in messages[2].content
    assert messages[-1].content == "There are 42 launches."
    assert fake_model.calls == 2


def test_graph_ends_without_calling_tools_when_the_model_just_answers(monkeypatch):
    monkeypatch.setattr(
        "chatbot_agent.nodes.chatbot.get_llm_with_tools",
        lambda: type("M", (), {"invoke": lambda self, m: AIMessage(content="Hello.")})(),
    )

    result = build_graph().invoke({"messages": [HumanMessage(content="hi")]})

    assert [type(m).__name__ for m in result["messages"]] == ["HumanMessage", "AIMessage"]
