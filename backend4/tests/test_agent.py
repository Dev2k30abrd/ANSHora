import json

import pytest

from app.core import config as cfg
from app.core import db
from app.core.context import workspace_scope
from app.llm import client as llm


@pytest.fixture
def live(monkeypatch, client, dataset):
    monkeypatch.setattr(cfg, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(cfg, "LLM_API_KEY", "x")
    llm._NO_TOOL_MODELS.clear()
    ws = db.one("SELECT workspace_id FROM datasets WHERE id=?", (dataset,))["workspace_id"]
    with workspace_scope(ws):
        yield dataset


def test_native_loop_with_verifier_retry(monkeypatch, live):
    from app.agents.agent import run_agent_stream

    calls = {"n": 0}

    def fake(messages, model=None, temperature=0.1, tools=None):
        calls["n"] += 1
        if calls["n"] == 1:
            yield {"type": "tool_calls", "calls": [{"id": "c1", "name": "group_analysis",
                   "arguments": {"group_column": "Region", "value_column": "Sales", "operation": "sum"}}]}
            yield {"type": "end", "content": ""}
        elif calls["n"] == 2:  # fabricated figures -> verifier must reject
            t = "West sells ₹98,76,543 and North ₹54,32,100, plus ₹77,77,777 elsewhere."
            yield {"type": "text", "delta": t}
            yield {"type": "end", "content": t}
        else:
            t = "West leads with 435,500."
            yield {"type": "text", "delta": t}
            yield {"type": "end", "content": t}

    monkeypatch.setattr(llm, "stream_chat", fake)
    evs = list(run_agent_stream("sales by region", live))
    types = [e["type"] for e in evs]
    assert "retract" in types
    done = evs[-1]
    assert done["verification"]["auto_corrected"] and done["verification"]["status"] == "verified"
    assert done["answer"].startswith("West leads")
    assert done["mode"] == "native"


def test_json_mode_fallback_when_tools_unsupported(monkeypatch, live):
    from app.agents.agent import run_agent_stream

    def fake_stream(messages, model=None, temperature=0.1, tools=None):
        if tools:
            raise llm.ToolsUnsupported("No endpoints found that support tool use")
        t = "Total West sales are 435,500."
        yield {"type": "text", "delta": t}
        yield {"type": "end", "content": t}

    seq = iter(['Sure!\n```json\n{"action":"tool","tool":"group_analysis","arguments":{"group_column":"Region","value_column":"Sales"},}\n```',
                '{"action":"final"}'])
    monkeypatch.setattr(llm, "stream_chat", fake_stream)
    monkeypatch.setattr(llm, "complete", lambda messages, model=None, temperature=0.2, tools=None: {"content": next(seq), "tool_calls": []})
    evs = list(run_agent_stream("sales by region", live))
    done = evs[-1]
    assert done["mode"] == "json"
    assert any(e["type"] == "tool_result" and e["ok"] for e in evs)
    assert done["verification"]["status"] == "verified"


def test_tool_error_is_recoverable(monkeypatch, live):
    from app.agents.agent import run_agent_stream

    n = {"i": 0}

    def fake(messages, model=None, temperature=0.1, tools=None):
        n["i"] += 1
        if n["i"] == 1:
            yield {"type": "tool_calls", "calls": [{"id": "a", "name": "sql_query", "arguments": {"query": "DELETE FROM data"}}]}
            yield {"type": "end", "content": ""}
        elif n["i"] == 2:
            tool_msg = [m for m in messages if m["role"] == "tool"][-1]["content"]
            assert "error" in tool_msg
            yield {"type": "tool_calls", "calls": [{"id": "b", "name": "sql_query", "arguments": {"query": "select count(*) c from data"}}]}
            yield {"type": "end", "content": ""}
        else:
            yield {"type": "text", "delta": "There are 60 rows."}
            yield {"type": "end", "content": "There are 60 rows."}

    monkeypatch.setattr(llm, "stream_chat", fake)
    evs = list(run_agent_stream("how many rows", live))
    res = [e for e in evs if e["type"] == "tool_result"]
    assert [r["ok"] for r in res] == [False, True]
    assert evs[-1]["confidence"]["score"] < 100


def test_openai_stream_parsing(monkeypatch):
    lines = [
        'data: {"choices":[{"delta":{"reasoning":"hmm"}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"t1","function":{"name":"sql_query","arguments":"{\\"query\\":"}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"select 1\\"}"}}]}}]}',
        "data: [DONE]",
    ]

    class R:
        ok = True

        def iter_lines(self):
            return [l.encode() for l in lines]

        def close(self):
            pass

    monkeypatch.setattr(cfg, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(cfg, "LLM_API_KEY", "x")
    monkeypatch.setattr(llm, "_post", lambda payload, stream: R())
    evs = list(llm.stream_chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}]))
    assert evs[0]["type"] == "thinking"
    tc = next(e for e in evs if e["type"] == "tool_calls")
    assert tc["calls"][0]["arguments"] == {"query": "select 1"}
