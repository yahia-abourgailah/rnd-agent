"""The SQL guard is the last line of defence in front of LLM-authored SQL, so
it is tested against the statements a model actually produces when it goes
wrong — not just the happy path."""

import pytest

from chatbot_agent.tools.postgres import UnsafeQueryError, assert_read_only, query_database

READ_ONLY_QUERIES = [
    "SELECT * FROM launches LIMIT 10",
    "select project_name from launches;",
    "WITH recent AS (SELECT * FROM launches) SELECT count(*) FROM recent",
    "-- count them\nSELECT count(*) FROM launches",
    "SELECT /* inline */ 1",
]

WRITE_QUERIES = [
    "DROP TABLE launches",
    "DELETE FROM launches",
    "UPDATE launches SET price_from = 0",
    "INSERT INTO launches (project_name) VALUES ('x')",
    "TRUNCATE launches",
    "ALTER TABLE launches DROP COLUMN zone",
    "GRANT ALL ON launches TO PUBLIC",
    "CREATE TABLE evil (id int)",
    "COPY launches TO '/tmp/leak.csv'",
]


@pytest.mark.parametrize("sql", READ_ONLY_QUERIES)
def test_read_only_queries_are_accepted(sql):
    assert assert_read_only(sql)


@pytest.mark.parametrize("sql", WRITE_QUERIES)
def test_write_statements_are_rejected(sql):
    with pytest.raises(UnsafeQueryError):
        assert_read_only(sql)


def test_statement_stacking_is_rejected():
    """A trailing write hidden behind a valid SELECT — Postgres would run both."""
    with pytest.raises(UnsafeQueryError):
        assert_read_only("SELECT 1; DROP TABLE launches")


def test_write_hidden_by_a_comment_is_rejected():
    """Comment stripping must happen before the statement count, or the second
    statement hides behind a block comment."""
    with pytest.raises(UnsafeQueryError):
        assert_read_only("SELECT 1 /* ; */; DELETE FROM launches")


def test_data_modifying_cte_is_rejected():
    with pytest.raises(UnsafeQueryError):
        assert_read_only("WITH gone AS (DELETE FROM launches RETURNING *) SELECT * FROM gone")


def test_empty_query_is_rejected():
    with pytest.raises(UnsafeQueryError):
        assert_read_only("   -- nothing here\n  ")


def test_trailing_semicolon_is_not_treated_as_a_second_statement():
    assert assert_read_only("SELECT 1;") == "SELECT 1"


def test_tool_returns_the_reason_instead_of_raising(monkeypatch):
    """The model needs a readable rejection to correct itself on the next turn,
    and the tool must never reach the database for a rejected query."""

    def fail_if_called(*args, **kwargs):
        raise AssertionError("engine must not be built for a rejected query")

    monkeypatch.setattr("chatbot_agent.tools.postgres.get_engine", fail_if_called)

    result = query_database.invoke({"query": "DROP TABLE launches"})

    assert "rejected" in result.lower()
