"""Regression tests for the accuracy problems found with a real LLM on data2.csv."""
import pytest

from app.core import config as cfg
from app.core import db
from app.core.context import workspace_scope
from app.llm import client as llm
from app.services.dataset_manager import dataset_store
from app.services.verifier import unsupported_claims, verify_answer


@pytest.fixture
def scope(client, dataset2):
    ws = db.one("SELECT workspace_id FROM datasets WHERE id=?", (dataset2,))["workspace_id"]
    with workspace_scope(ws):
        yield dataset2


def test_duplicates_excluded_from_analysis_but_reported(scope):
    assert len(dataset_store.get_raw(scope)) == 31
    assert len(dataset_store.get(scope)) == 30
    assert dataset_store.duplicates_excluded(scope) == 1


def test_duplicate_toggle_api(client, auth, dataset2):
    r = client.patch(f"/api/dataset/{dataset2}/settings", json={"exclude_duplicates": False}, headers=auth)
    assert r.json()["duplicates_excluded"] == 0
    assert client.get(f"/api/profit/{dataset2}", headers=auth).json()["headline"]["revenue"] == 996800
    client.patch(f"/api/dataset/{dataset2}/settings", json={"exclude_duplicates": True}, headers=auth)
    j = client.get(f"/api/profit/{dataset2}", headers=auth).json()
    assert j["headline"]["revenue"] == 908800 and j["headline"]["profit"] == 156750


def test_profit_engine_on_data2(client, auth, dataset2):
    j = client.get(f"/api/profit/{dataset2}", headers=auth).json()
    assert round(j["headline"]["margin_pct"], 2) == 16.85          # weighted, complete rows
    assert any("duplicate" in n for n in j["notes"])
    assert not any("previous week" in f["title"] for f in j["findings"])  # no weekly noise on 31 rows
    assert j["capabilities"]["discount"] is None and j["capabilities"]["cost"].endswith("(derived)")


def test_summary_reports_raw_duplicates(client, auth, dataset2):
    s = client.get(f"/api/dataset/{dataset2}/summary", headers=auth).json()
    assert s["duplicate_rows"] == 1 and s["rows"] == 31 and s["duplicates_excluded"] == 1


def test_facts_sheet(scope):
    from app.services.facts import build_facts, question_hints

    f = build_facts(scope)
    assert "OVERALL MARGIN" in f["text"] and "16.85%" in f["text"]
    assert "NOT AVAILABLE" in f["text"] and "discount" in f["text"]
    assert 16.85 in [round(n, 2) for n in f["numbers"]]
    assert "NO discount column" in question_hints("How much revenue do we leak through discounts?", f["capabilities"])
    assert question_hints("Which region has the best margin?", f["capabilities"]) == ""


def test_unsupported_claim_detector():
    caps = {"discount": None, "returns": None, "churn": None}
    bad = ("Roughly ₹808k of the revenue is not profit – this pool covers cost of goods, discounts, returns, "
           "and other leakage.")
    assert unsupported_claims(bad, caps)
    ok = "The data has no discount column, so discount leakage of any amount cannot be measured."
    assert unsupported_claims(ok, caps) == []
    assert unsupported_claims(bad, {"discount": "Discount", "returns": "R"}) == []


def test_verifier_rejects_row_average_margin():
    facts = {"facts": [16.85, 908800.0, 156750.0]}
    v = verify_answer("The average profit margin is 18.95% on ₹9.09 L sales.", [facts])
    assert any("18.95" in u["text"] for u in v["unverified"])
    assert verify_answer("The margin is 16.85% on ₹9.09 L sales.", [facts])["status"] == "verified"


def test_agent_rewrites_hallucinated_discount_answer(monkeypatch, scope):
    """Reproduces the screenshot: model invents a ₹8.08 L 'discount' leak on a dataset with no discount column."""
    from app.agents.agent import run_agent_stream

    monkeypatch.setattr(cfg, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(cfg, "LLM_API_KEY", "x")
    llm._NO_TOOL_MODELS.clear()
    seen = {"n": 0, "last_user": ""}

    def fake(messages, model=None, temperature=0.1, tools=None):
        seen["n"] += 1
        seen["last_user"] = messages[-1]["content"]
        if seen["n"] == 1:
            assert "NO discount column" in messages[-1]["content"]      # hint reached the model
            assert "FACTS SHEET" in messages[0]["content"]
            t = ("Roughly ₹8.08 L of revenue is not profit – this pool covers cost of goods, discounts, returns "
                 "and other leakage. Average margin is 18.95%.")
        else:
            t = ("Discount leakage cannot be measured: the dataset has no discount column. "
                 "Margin is 16.85% on ₹9.09 L sales. Add a list-price or discount column to measure it.")
        yield {"type": "text", "delta": t}
        yield {"type": "end", "content": t}

    monkeypatch.setattr(llm, "stream_chat", fake)
    evs = list(run_agent_stream("How much revenue do we leak through discounts?", scope))
    done = evs[-1]
    assert "retract" in [e["type"] for e in evs]
    assert done["verification"]["auto_corrected"] and done["verification"]["unsupported"] == []
    assert "cannot be measured" in done["answer"]
    assert "Rewrite your answer" in seen["last_user"]


def test_insights_no_longer_call_cheap_items_underperformers(client, auth, dataset2):
    j = client.get(f"/api/insights/{dataset2}/proactive?refresh=true", headers=auth).json()
    assert not any(f["type"] == "risk" and "underperform" in f["title"] for f in j["findings"])
    conc = [f for f in j["findings"] if f["type"] == "concentration" and "Corporate" in f["title"]]
    assert conc and "63.77%" in conc[0]["title"] and "no Customer_Segment label" in conc[0]["title"]
