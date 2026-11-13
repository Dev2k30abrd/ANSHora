"""
Tests for Agent Loop Reliability, duplicate call prevention,
circuit breakers, and stopping conditions.
"""
import pytest
from app.agents.agent import _call_signature, run_agent_stream
from app.core import config as cfg
from app.core import db
from app.core.context import workspace_scope
from app.llm import client as llm


@pytest.fixture
def live_scope(monkeypatch, client, dataset):
    monkeypatch.setattr(cfg, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(cfg, "LLM_API_KEY", "x")
    llm._NO_TOOL_MODELS.clear()
    ws = db.one("SELECT workspace_id FROM datasets WHERE id=?", (dataset,))["workspace_id"]
    with workspace_scope(ws):
        yield dataset


def test_call_signature():
    sig1 = _call_signature("group_analysis", {"group_column": "Region", "value_column": "Sales"})
    sig2 = _call_signature("group_analysis", {"value_column": "Sales", "group_column": "Region"})
    assert sig1 == sig2
    assert "group_analysis" in sig1


def test_agent_loop_detects_and_prevents_duplicate_tool_calls(monkeypatch, live_scope):
    """The agent loop must detect duplicate calls with identical arguments and not re-execute."""
    dataset_id = live_scope
    actual_executions = {"count": 0}

    # Intercept reg.timed_run to count actual tool executions
    from app.agents import tools_registry as reg
    orig_timed_run = reg.timed_run

    def counting_timed_run(name, args, ds_id):
        actual_executions["count"] += 1
        return orig_timed_run(name, args, ds_id)

    monkeypatch.setattr(reg, "timed_run", counting_timed_run)

    step_counter = {"n": 0}

    def fake_stream(messages, model=None, temperature=0.1, tools=None):
        step_counter["n"] += 1
        if step_counter["n"] == 1:
            # First call to group_analysis
            yield {
                "type": "tool_calls",
                "calls": [{
                    "id": "c1",
                    "name": "group_analysis",
                    "arguments": {"group_column": "Region", "value_column": "Sales", "operation": "sum"},
                }],
            }
            yield {"type": "end", "content": ""}
        elif step_counter["n"] == 2:
            # Model attempts the EXACT duplicate tool call
            yield {
                "type": "tool_calls",
                "calls": [{
                    "id": "c2",
                    "name": "group_analysis",
                    "arguments": {"group_column": "Region", "value_column": "Sales", "operation": "sum"},
                }],
            }
            yield {"type": "end", "content": ""}
        else:
            # Final answer
            t = "Total sales for West is 435,500 and North is 280,000."
            yield {"type": "text", "delta": t}
            yield {"type": "end", "content": t}

    monkeypatch.setattr(llm, "stream_chat", fake_stream)

    evs = list(run_agent_stream("sales by region", dataset_id))
    # Even though model requested 2 calls, actual tool execution should happen only ONCE!
    assert actual_executions["count"] == 1

    tool_results = [e for e in evs if e["type"] == "tool_result"]
    assert len(tool_results) == 2  # UI gets both results cleanly


def test_agent_loop_circuit_breaker_on_repeated_failures(monkeypatch, live_scope):
    """If tools fail repeatedly, circuit breaker must stop loop and synthesize answer."""
    dataset_id = live_scope

    from app.agents import tools_registry as reg

    def failing_timed_run(name, args, ds_id):
        return False, {"error": "Simulated hardware error"}, 10

    monkeypatch.setattr(reg, "timed_run", failing_timed_run)

    step_counter = {"n": 0}

    def fake_stream(messages, model=None, temperature=0.1, tools=None):
        step_counter["n"] += 1
        if tools:
            # Model persistently calls broken tool
            yield {
                "type": "tool_calls",
                "calls": [{"id": f"c_{step_counter['n']}", "name": "basic_statistics", "arguments": {}}],
            }
            yield {"type": "end", "content": ""}
        else:
            t = "The requested calculations could not be performed due to an analytics failure."
            yield {"type": "text", "delta": t}
            yield {"type": "end", "content": t}

    monkeypatch.setattr(llm, "stream_chat", fake_stream)

    evs = list(run_agent_stream("overview", dataset_id))
    done = evs[-1]
    assert done["type"] == "done"
    # Must stop within max failures rather than running indefinitely
    assert len(done["tool_runs"]) <= 3
