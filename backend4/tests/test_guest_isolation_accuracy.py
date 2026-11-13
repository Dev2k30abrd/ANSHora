"""
Comprehensive tests for:
1. Guest Chat Isolation & Fresh Launch
2. Multi-Tenant User Isolation
3. Analytical Accuracy on Quantity x UnitPrice & Negative Transaction Cancellations
"""
import pytest
import pandas as pd
from app.core import db
from app.services.profit_engine import analyze_profit_impact, detect_financial_columns
from app.services.dataset_manager import dataset_store


def test_guest_chat_isolation_and_no_leakage(client, auth, auth2):
    """
    Verifies that:
    1. Unauthenticated requests to /api/chats return 401.
    2. Guest user cannot see chats of User A or User B.
    3. User A and User B workspaces are strictly isolated.
    """
    # 1. Unauthenticated request rejected
    res = client.get("/api/chats")
    assert res.status_code == 401

    # 2. User A creates a chat
    ds_a = client.post("/api/dataset/sample/sales_data.csv", headers=auth).json()["dataset_id"]
    chat_a = client.post("/api/chats", json={"dataset_id": ds_a, "title": "User A Chat"}, headers=auth).json()["chat"]
    assert chat_a["title"] == "User A Chat"

    # 3. User B cannot see User A's chat
    b_chats = client.get("/api/chats", headers=auth2).json()["chats"]
    assert all(c["id"] != chat_a["id"] for c in b_chats)

    # 4. User B cannot read User A's chat by ID
    res_b_read = client.get(f"/api/chats/{chat_a['id']}", headers=auth2)
    assert res_b_read.status_code == 404

    # 5. Guest session created
    guest = client.post("/api/auth/guest").json()
    guest_auth = {"Authorization": f"Bearer {guest['token']}"}

    # Guest cannot see User A's or User B's chats
    guest_chats = client.get("/api/chats", headers=guest_auth).json()["chats"]
    assert all(c["id"] != chat_a["id"] for c in guest_chats)


def test_derived_revenue_calculation():
    """
    Verifies that a dataset with Quantity and UnitPrice (and no Revenue column)
    correctly derives Revenue = Quantity * UnitPrice and discloses it as derived.
    """
    df = pd.DataFrame({
        "InvoiceNo": ["1001", "1002", "1003"],
        "Quantity": [10, 5, 2],
        "UnitPrice": [20.0, 50.0, 100.0],
        "Country": ["UK", "UK", "France"]
    })
    # Expected revenue: 10*20 + 5*50 + 2*100 = 200 + 250 + 200 = 650
    cols = detect_financial_columns(df)
    assert cols["quantity"] == "Quantity"
    assert cols["price"] == "UnitPrice"
    assert cols["revenue"] is None

    res = analyze_profit_impact(df, currency="£")
    assert res["mode"] == "revenue_only"
    assert res["headline"]["revenue"] == 650.0
    assert "Quantity × UnitPrice (derived)" in res["capabilities"]["revenue"]
    assert any("Quantity × UnitPrice" in n for n in res["notes"])
    assert res["headline"]["cost"] is None
    assert res["headline"]["profit"] is None
    assert res["headline"]["margin_pct"] is None


def test_cancellation_and_negative_transaction_leakage():
    """
    Verifies that negative transactions (cancellations/refunds) are detected as leakages
    and reported with exact count and sum without hallucinating profit.
    """
    df = pd.DataFrame({
        "InvoiceNo": ["1001", "1002", "C1003"],
        "Quantity": [10, 20, -5],
        "UnitPrice": [10.0, 10.0, 10.0],
        "Country": ["UK", "UK", "UK"]
    })
    # Gross: 100 + 200 = 300
    # Cancellations: -50
    # Net: 250
    res = analyze_profit_impact(df, currency="£")
    assert res["headline"]["revenue"] == 250.0
    cancellation_finding = next((f for f in res["findings"] if f["id"] == "leak::cancellations"), None)
    assert cancellation_finding is not None
    assert cancellation_finding["impact_amount"] == 50.0
    assert "1 return/cancellation transaction(s)" in cancellation_finding["detail"]
