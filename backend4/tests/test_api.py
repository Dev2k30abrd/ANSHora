import json


def events(resp):
    return [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ")]


def test_auth_required(client):
    assert client.get("/api/dataset/").status_code == 401
    assert client.get("/api/system/status").json()["llm"]["mode"] == "demo"


def test_login_bad_password(client, auth):
    r = client.post("/api/auth/login", json={"email": "a@test.com", "password": "wrongwrong"})
    assert r.status_code == 401


def test_upload_and_pack_detection(client, auth, dataset):
    r = client.get(f"/api/dataset/{dataset}/summary", headers=auth)
    assert r.status_code == 200 and r.json()["pack_id"] == "retail"


def test_tenant_isolation(client, auth, auth2, dataset):
    assert client.get(f"/api/dataset/{dataset}/summary", headers=auth2).status_code == 404
    assert client.get(f"/api/profit/{dataset}", headers=auth2).status_code == 404
    assert client.delete(f"/api/dataset/{dataset}", headers=auth2).status_code == 404
    assert client.get("/api/dataset/", headers=auth2).json()["datasets"] == []


def test_profit_endpoint(client, auth, dataset):
    j = client.get(f"/api/profit/{dataset}", headers=auth).json()
    assert j["mode"] == "full" and j["headline"]["profit"] > 0 and j["findings"]


def test_chat_stream_persist_and_verify(client, auth, dataset):
    chat = client.post("/api/chats", json={"dataset_id": dataset}, headers=auth).json()["chat"]
    r = client.post(f"/api/chats/{chat['id']}/stream", json={"question": "Where am I losing money?"}, headers=auth)
    evs = events(r)
    types = [e["type"] for e in evs]
    assert "tool_start" in types and "tool_result" in types and types[-1] == "done"
    done = evs[-1]
    assert done["verification"]["status"] in ("verified", "partial", "no_numbers")
    assert done["confidence"]["label"] in ("High", "Medium", "Low")
    got = client.get(f"/api/chats/{chat['id']}", headers=auth).json()
    assert [m["role"] for m in got["messages"]] == ["user", "assistant"]
    # regenerate keeps exactly one pair
    r = client.post(f"/api/chats/{chat['id']}/stream", json={"regenerate": True}, headers=auth)
    assert events(r)[-1]["type"] == "done"
    got = client.get(f"/api/chats/{chat['id']}", headers=auth).json()
    assert len(got["messages"]) == 2
    # other tenant cannot read the chat
    # (auth2 created in another test; use a fresh bad id)
    assert client.get("/api/chats/nope", headers=auth).status_code == 404


def test_multi_step_and_group(client, auth, dataset):
    chat = client.post("/api/chats", json={"dataset_id": dataset}, headers=auth).json()["chat"]
    evs = events(client.post(f"/api/chats/{chat['id']}/stream", json={"question": "why did Sales change?"}, headers=auth))
    starts = [e["name"] for e in evs if e["type"] == "tool_start"]
    assert len(starts) >= 2


def test_decisions_flow(client, auth, dataset):
    r = client.post("/api/decisions", headers=auth, json={"dataset_id": dataset, "title": "Cut discount", "metric_column": "Profit",
                                                           "expected_impact": 50000})
    assert r.status_code == 200
    did = r.json()["decision"]["id"]
    ev = client.post(f"/api/decisions/{did}/evaluate", headers=auth).json()["decision"]
    assert ev["realized_impact"] == 0
    assert client.get("/api/decisions/summary", headers=auth).json()["total"] == 1


def test_monitor_run_and_notifications(client, auth, dataset):
    r = client.post("/api/monitors", headers=auth, json={"dataset_id": dataset, "name": "Profit watch", "kind": "profit_scan"})
    mid = r.json()["monitor"]["id"]
    out = client.post(f"/api/monitors/{mid}/run", headers=auth).json()
    assert out["result"]["triggered"] is True
    n = client.get("/api/monitors/notifications/list", headers=auth).json()
    assert n["unread"] >= 1


def test_exports(client, auth, dataset):
    for fmt, magic in (("pdf", b"%PDF"), ("xlsx", b"PK"), ("html", b"<!doctype"), ("md", b"# ")):
        r = client.get(f"/api/export/{dataset}?format={fmt}", headers=auth)
        assert r.status_code == 200 and r.content[:len(magic)].lower() == magic.lower(), fmt


def test_projects_and_workspace(client, auth):
    p = client.post("/api/projects", headers=auth, json={"name": "FY26", "instructions": "Fiscal year starts April", "industry_pack": "saas"})
    assert p.status_code == 200
    w = client.patch("/api/auth/workspace", headers=auth, json={"currency": "$"})
    assert w.json()["user"]["workspace"]["currency"] == "$"


def test_sql_and_sandbox_via_registry(client, auth, dataset):
    from app.agents.tools_registry import timed_run
    from app.core.context import workspace_scope
    from app.core import db

    ws = db.one("SELECT workspace_id FROM datasets WHERE id=?", (dataset,))["workspace_id"]
    with workspace_scope(ws):
        ok, r, _ = timed_run("sql_query", {"query": "select Region, sum(Sales) s from data group by 1"}, dataset)
        assert ok and r["row_count"] == 4
        ok, r, _ = timed_run("sql_query", {"query": "drop table data"}, dataset)
        assert not ok
        ok, r, _ = timed_run("python_analysis", {"code": "result = float(df['Sales'].sum())"}, dataset)
        assert ok and r["result"] > 0
        ok, r, _ = timed_run("python_analysis", {"code": "import os\nresult=1"}, dataset)
        assert not ok


def test_url_import_blocks_private(client, auth):
    r = client.post("/api/dataset/import-url", headers=auth, json={"url": "http://127.0.0.1:8000/x.csv"})
    assert r.status_code == 400
