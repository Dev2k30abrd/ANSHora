"""
Comprehensive Phase 2 Security, Authentication, Tenancy, and Persistence Test Suite.

Validates:
1. Google Sign-In (URL generation, CSRF state protection, token claim verification, new user provisioning, existing account linking).
2. Guest Mode (ephemeral workspace, guest role, isolation).
3. Workspace Management (list, create, update, switch active, delete protection).
4. Multi-Tenant Cross-Access Isolation (workspaces, datasets, chats, projects, decisions, reports).
5. Chat Search & Guest Isolation (persistent vs guest chat visibility).
6. Business Memory Engine (record, search, cross-workspace isolation).
7. Executive Report Relational Persistence (save, retrieve, delete, cross-workspace isolation).
8. Gmail Regression (preview token creation and validation intact).
"""
import time
from unittest.mock import patch

import jwt
import pytest

from app.core import config as cfg
from app.core import db
from app.core.security import create_token
from app.services.google_auth_service import (
    create_google_authorization_url,
    process_google_callback,
    verify_id_token_claims,
)
from app.services.business_memory import record_memory, search_memory, get_workspace_memories
from app.services.gmail_service import prepare_email_preview


# ==============================================================================
# 1. GOOGLE SIGN-IN & GUEST AUTHENTICATION TESTS
# ==============================================================================

def test_google_authorize_url_generation(client, monkeypatch):
    monkeypatch.setattr(cfg, "GOOGLE_SIGNIN_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    res = create_google_authorization_url(return_to="http://localhost:5173/dashboard")
    assert "url" in res
    assert "state" in res
    assert "accounts.google.com" in res["url"]
    assert "test-client-id" in res["url"]
    assert "openid" in res["url"]
    assert "email" in res["url"]
    assert "profile" in res["url"]
    assert f"state={res['state']}" in res["url"]

    # Verify state was recorded in DB
    state_row = db.one("SELECT * FROM oauth_states WHERE state=?", (res["state"],))
    assert state_row is not None
    assert state_row["redirect_url"] == "http://localhost:5173/dashboard"


def test_google_callback_invalid_state(client):
    r = client.get("/api/auth/google/callback?code=fake_code&state=non_existent_state", headers={"Accept": "application/json"})
    assert r.status_code == 400
    assert "state" in r.text.lower()


def test_google_callback_error_query(client):
    r = client.get("/api/auth/google/callback?error=access_denied", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "auth_error=access_denied" in r.headers["location"]


def test_verify_id_token_claims_validation(monkeypatch):
    client_id = "test-client-123.apps.googleusercontent.com"
    monkeypatch.setattr(cfg, "GOOGLE_SIGNIN_CLIENT_ID", client_id)

    # 1. Untrusted issuer
    bad_iss_token = jwt.encode({"iss": "evil.com", "aud": client_id, "exp": time.time() + 3600, "email_verified": True}, "secret")
    with pytest.raises(Exception) as exc:
        verify_id_token_claims(bad_iss_token, client_id)
    assert "Untrusted token issuer" in str(exc.value)

    # 2. Audience mismatch
    bad_aud_token = jwt.encode({"iss": "https://accounts.google.com", "aud": "wrong-client", "exp": time.time() + 3600, "email_verified": True}, "secret")
    with pytest.raises(Exception) as exc:
        verify_id_token_claims(bad_aud_token, client_id)
    assert "audience mismatch" in str(exc.value)

    # 3. Expired token
    expired_token = jwt.encode({"iss": "https://accounts.google.com", "aud": client_id, "exp": time.time() - 3600, "email_verified": True}, "secret")
    with pytest.raises(Exception) as exc:
        verify_id_token_claims(expired_token, client_id)
    assert "expired" in str(exc.value).lower()

    # 4. Unverified email
    unverified_token = jwt.encode({"iss": "https://accounts.google.com", "aud": client_id, "exp": time.time() + 3600, "email_verified": False}, "secret")
    with pytest.raises(Exception) as exc:
        verify_id_token_claims(unverified_token, client_id)
    assert "not verified" in str(exc.value).lower()

    # 5. Valid token
    valid_token = jwt.encode({
        "iss": "https://accounts.google.com",
        "aud": client_id,
        "exp": time.time() + 3600,
        "email_verified": True,
        "sub": "sub-12345",
        "email": "verified@example.com",
        "name": "Verified User",
    }, "secret")
    claims = verify_id_token_claims(valid_token, client_id)
    assert claims["email"] == "verified@example.com"
    assert claims["sub"] == "sub-12345"


def test_google_verify_new_user_provisioning(client, monkeypatch):
    client_id = "test-client-123.apps.googleusercontent.com"
    monkeypatch.setattr(cfg, "GOOGLE_SIGNIN_CLIENT_ID", client_id)

    fake_id_token = jwt.encode({
        "iss": "https://accounts.google.com",
        "aud": client_id,
        "exp": time.time() + 3600,
        "email_verified": True,
        "sub": "google-unique-998877",
        "email": "google_newbie@anshora.io",
        "name": "Google Newbie",
        "picture": "https://example.com/avatar.png",
    }, "secret")

    r = client.post("/api/auth/google/verify", json={"id_token": fake_id_token})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data
    assert data["user"]["email"] == "google_newbie@anshora.io"
    assert data["user"]["name"] == "Google Newbie"

    # Verify user exists in database with workspace and oauth identity
    user_row = db.one("SELECT * FROM users WHERE email=?", ("google_newbie@anshora.io",))
    assert user_row is not None
    assert user_row["google_subject_id"] == "google-unique-998877"

    ws_row = db.one("SELECT * FROM workspaces WHERE id=?", (user_row["workspace_id"],))
    assert ws_row is not None
    assert "Google Newbie" in ws_row["name"]

    identity_row = db.one("SELECT * FROM oauth_identities WHERE user_id=? AND provider='google'", (user_row["id"],))
    assert identity_row is not None
    assert identity_row["provider_user_id"] == "google-unique-998877"


def test_google_verify_existing_user_linking(client, monkeypatch):
    client_id = "test-client-123.apps.googleusercontent.com"
    monkeypatch.setattr(cfg, "GOOGLE_SIGNIN_CLIENT_ID", client_id)

    # 1. Register a standard user
    reg = client.post("/api/auth/register", json={
        "email": "local_first@anshora.io",
        "name": "Local First",
        "password": "Password123!",
    })
    assert reg.status_code == 200
    original_user_id = reg.json()["user"]["id"]
    original_ws_id = reg.json()["user"]["workspace"]["id"]

    # 2. Verify with Google ID token matching that email
    fake_id_token = jwt.encode({
        "iss": "https://accounts.google.com",
        "aud": client_id,
        "exp": time.time() + 3600,
        "email_verified": True,
        "sub": "google-linked-445566",
        "email": "local_first@anshora.io",
        "name": "Local First",
    }, "secret")

    r = client.post("/api/auth/google/verify", json={"id_token": fake_id_token})
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["id"] == original_user_id
    assert data["user"]["workspace"]["id"] == original_ws_id

    # Check updated database record
    user_row = db.one("SELECT * FROM users WHERE id=?", (original_user_id,))
    assert user_row["google_subject_id"] == "google-linked-445566"


def test_google_authorize_url_generation(client, monkeypatch):
    client_id = "test-client-123.apps.googleusercontent.com"
    monkeypatch.setattr(cfg, "GOOGLE_SIGNIN_CLIENT_ID", client_id)

    # 1. With Gmail onboarding enabled (default)
    r1 = client.get("/api/auth/google/authorize?include_gmail=true")
    assert r1.status_code == 200
    data1 = r1.json()
    from urllib.parse import unquote
    unquoted_url = unquote(data1["url"])
    assert "https://www.googleapis.com/auth/gmail.send" in unquoted_url
    assert "prompt=consent select_account" in unquoted_url or "prompt=consent+select_account" in data1["url"]
    assert "include_granted_scopes=true" in unquoted_url

    # 2. Without Gmail onboarding
    r2 = client.get("/api/auth/google/authorize?include_gmail=false")
    assert r2.status_code == 200
    data2 = r2.json()
    assert "gmail.send" not in data2["url"]


def test_google_callback_with_gmail_consent(client, monkeypatch):
    client_id = "test-client-123.apps.googleusercontent.com"
    monkeypatch.setattr(cfg, "GOOGLE_SIGNIN_CLIENT_ID", client_id)
    monkeypatch.setattr(cfg, "GOOGLE_SIGNIN_CLIENT_SECRET", "test-secret")

    # Initiate state
    auth_resp = client.get("/api/auth/google/authorize")
    state = auth_resp.json()["state"]

    fake_id_token = jwt.encode({
        "iss": "https://accounts.google.com",
        "aud": client_id,
        "exp": time.time() + 3600,
        "email_verified": True,
        "sub": "google-gmail-consented-1122",
        "email": "gmail_consented@anshora.io",
        "name": "Gmail Consented User",
    }, "secret")

    class MockResponse:
        ok = True
        status_code = 200
        def json(self):
            return {
                "id_token": fake_id_token,
                "access_token": "ya29.mock_access_token",
                "refresh_token": "1//mock_refresh_token",
                "expires_in": 3600,
                "scope": "openid email profile https://www.googleapis.com/auth/gmail.send",
            }

    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **kw: MockResponse())

    # Call callback with json accept header
    r = client.get(f"/api/auth/google/callback?code=mock_code&state={state}", headers={"Accept": "application/json"})
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data["gmail_connected"] is True
    ws_id = data["user"]["workspace"]["id"]

    # Verify gmail_integrations table was populated
    gmail_row = db.one("SELECT * FROM gmail_integrations WHERE workspace_id=?", (ws_id,))
    assert gmail_row is not None
    assert gmail_row["refresh_token"] == "1//mock_refresh_token"
    assert gmail_row["email"] == "gmail_consented@anshora.io"


def test_google_callback_with_gmail_declined(client, monkeypatch):
    client_id = "test-client-123.apps.googleusercontent.com"
    monkeypatch.setattr(cfg, "GOOGLE_SIGNIN_CLIENT_ID", client_id)
    monkeypatch.setattr(cfg, "GOOGLE_SIGNIN_CLIENT_SECRET", "test-secret")

    auth_resp = client.get("/api/auth/google/authorize")
    state = auth_resp.json()["state"]

    fake_id_token = jwt.encode({
        "iss": "https://accounts.google.com",
        "aud": client_id,
        "exp": time.time() + 3600,
        "email_verified": True,
        "sub": "google-gmail-declined-3344",
        "email": "gmail_declined@anshora.io",
        "name": "Gmail Declined User",
    }, "secret")

    class MockResponse:
        ok = True
        status_code = 200
        def json(self):
            return {
                "id_token": fake_id_token,
                "access_token": "ya29.mock_access_token",
                "refresh_token": None,
                "expires_in": 3600,
                "scope": "openid email profile",  # User only granted identity!
            }

    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **kw: MockResponse())

    r = client.get(f"/api/auth/google/callback?code=mock_code&state={state}", headers={"Accept": "application/json"})
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data["gmail_connected"] is False
    ws_id = data["user"]["workspace"]["id"]

    # Verify gmail_integrations table was NOT populated
    gmail_row = db.one("SELECT * FROM gmail_integrations WHERE workspace_id=?", (ws_id,))
    assert gmail_row is None


def test_guest_session_creation(client):
    r = client.post("/api/auth/guest")
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data["user"]["role"] == "guest"
    assert "guest_" in data["user"]["email"]

    # Call /api/auth/me with guest token
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['token']}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["role"] == "guest"


# ==============================================================================
# 2. WORKSPACE MANAGEMENT TESTS
# ==============================================================================

def test_workspace_crud_lifecycle(client, auth):
    # 1. List workspaces (should have at least the primary one)
    r1 = client.get("/api/workspaces", headers=auth)
    assert r1.status_code == 200
    workspaces = r1.json()["workspaces"]
    assert len(workspaces) >= 1
    primary_id = r1.json()["active_workspace_id"]

    # 2. Create secondary workspace
    r2 = client.post("/api/workspaces", json={
        "name": "Operations Hub",
        "currency": "EUR",
        "industry_pack": "general",
    }, headers=auth)
    assert r2.status_code == 200
    new_ws = r2.json()["workspace"]
    new_ws_id = new_ws["id"]
    assert new_ws["name"] == "Operations Hub"
    assert new_ws["currency"] == "EUR"

    # 3. Get workspace details and stats
    r3 = client.get(f"/api/workspaces/{new_ws_id}", headers=auth)
    assert r3.status_code == 200
    assert r3.json()["workspace"]["name"] == "Operations Hub"
    assert "stats" in r3.json()

    # 4. Update/Rename workspace
    r4 = client.patch(f"/api/workspaces/{new_ws_id}", json={
        "name": "Global Operations Hub",
        "currency": "GBP",
    }, headers=auth)
    assert r4.status_code == 200
    assert r4.json()["workspace"]["name"] == "Global Operations Hub"
    assert r4.json()["workspace"]["currency"] == "GBP"

    # 5. Switch active workspace
    r5 = client.post(f"/api/workspaces/{new_ws_id}/switch", headers=auth)
    assert r5.status_code == 200
    new_token = r5.json()["token"]
    assert r5.json()["user"]["workspace"]["id"] == new_ws_id

    # Verify /api/auth/me reflects switched workspace
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert me.json()["user"]["workspace"]["id"] == new_ws_id

    # 6. Switch back to primary workspace
    r6 = client.post(f"/api/workspaces/{primary_id}/switch", headers={"Authorization": f"Bearer {new_token}"})
    assert r6.status_code == 200
    primary_token = r6.json()["token"]

    # 7. Delete secondary workspace
    r7 = client.delete(f"/api/workspaces/{new_ws_id}", headers={"Authorization": f"Bearer {primary_token}"})
    assert r7.status_code == 200
    assert r7.json()["ok"] is True

    # Verify it is deleted
    r8 = client.get(f"/api/workspaces/{new_ws_id}", headers={"Authorization": f"Bearer {primary_token}"})
    assert r8.status_code in (403, 404)


def test_cannot_delete_only_workspace(client):
    # Register fresh user with single workspace
    reg = client.post("/api/auth/register", json={
        "email": "single_ws_user@anshora.io",
        "name": "Single WS",
        "password": "Password123!",
    })
    token = reg.json()["token"]
    ws_id = reg.json()["user"]["workspace"]["id"]
    h = {"Authorization": f"Bearer {token}"}

    del_resp = client.delete(f"/api/workspaces/{ws_id}", headers=h)
    assert del_resp.status_code == 400
    assert "only workspace" in del_resp.text.lower()


# ==============================================================================
# 3. MULTI-TENANT ISOLATION TESTS (CROSS-TENANT ACCESS GUARDS)
# ==============================================================================

def test_cross_tenant_workspace_isolation(client, auth, auth2):
    # auth is User A; auth2 is User B
    # Get User B's active workspace
    ws_b = client.get("/api/workspaces", headers=auth2).json()["active_workspace_id"]

    # User A tries to view User B's workspace -> 403
    r_get = client.get(f"/api/workspaces/{ws_b}", headers=auth)
    assert r_get.status_code == 403

    # User A tries to update User B's workspace -> 403
    r_patch = client.patch(f"/api/workspaces/{ws_b}", json={"name": "Hacked"}, headers=auth)
    assert r_patch.status_code == 403

    # User A tries to switch to User B's workspace -> 403
    r_switch = client.post(f"/api/workspaces/{ws_b}/switch", headers=auth)
    assert r_switch.status_code == 403

    # User A tries to delete User B's workspace -> 403
    r_del = client.delete(f"/api/workspaces/{ws_b}", headers=auth)
    assert r_del.status_code == 403


def test_cross_tenant_dataset_isolation(client, auth, auth2, dataset):
    # dataset belongs to User A (via auth fixture)
    # User B (auth2) tries to access dataset -> 404 (not in User B's workspace)
    r_summary = client.get(f"/api/dataset/{dataset}/summary", headers=auth2)
    assert r_summary.status_code == 404

    # User B tries to delete User A's dataset -> 404
    r_del = client.delete(f"/api/dataset/{dataset}", headers=auth2)
    assert r_del.status_code == 404

    # User B's list_datasets should NOT include User A's dataset
    r_list = client.get("/api/dataset/", headers=auth2)
    assert r_list.status_code == 200
    b_dataset_ids = [d["id"] for d in r_list.json()["datasets"]]
    assert dataset not in b_dataset_ids


def test_cross_tenant_chat_isolation(client, auth, auth2, dataset):
    # User A creates a chat
    c_resp = client.post("/api/chats", json={"dataset_id": dataset, "title": "User A Sensitive Chat"}, headers=auth)
    assert c_resp.status_code == 200
    chat_a_id = c_resp.json()["chat"]["id"]

    # User B tries to read User A's chat -> 404
    r_get = client.get(f"/api/chats/{chat_a_id}", headers=auth2)
    assert r_get.status_code == 404

    # User B tries to rename User A's chat -> 404
    r_patch = client.patch(f"/api/chats/{chat_a_id}", json={"title": "Hacked"}, headers=auth2)
    assert r_patch.status_code == 404

    # User B tries to delete User A's chat -> 404
    r_del = client.delete(f"/api/chats/{chat_a_id}", headers=auth2)
    assert r_del.status_code == 404

    # User B's list_chats must not show User A's chat
    r_list = client.get("/api/chats", headers=auth2)
    assert r_list.status_code == 200
    assert all(c["id"] != chat_a_id for c in r_list.json()["chats"])


def test_cross_tenant_project_isolation(client, auth, auth2):
    # User A creates a project
    p_resp = client.post("/api/projects", json={"name": "Project Alpha Secret"}, headers=auth)
    assert p_resp.status_code == 200
    project_a_id = p_resp.json()["project"]["id"]

    # User B tries to access User A's project -> 404
    r_get = client.get(f"/api/projects/{project_a_id}", headers=auth2)
    assert r_get.status_code == 404

    # User B's project list must not contain Project Alpha
    r_list = client.get("/api/projects", headers=auth2)
    assert all(p["id"] != project_a_id for p in r_list.json()["projects"])


def test_cross_tenant_decision_isolation(client, auth, auth2, dataset):
    # User A logs a decision
    d_resp = client.post("/api/decisions", json={
        "dataset_id": dataset,
        "title": "Cut Marketing Spend by 25%",
        "expected_impact": 50000.0,
    }, headers=auth)
    assert d_resp.status_code == 200
    dec_id = d_resp.json()["decision"]["id"]

    # User B tries to record outcome for User A's decision -> 404
    r_outcome = client.post(f"/api/decisions/{dec_id}/outcome", json={
        "status": "Completed",
        "actual_outcome": "Saved 45k",
        "measured_impact": 45000.0,
    }, headers=auth2)
    assert r_outcome.status_code == 404


# ==============================================================================
# 4. CHAT SEARCH & GUEST ISOLATION TESTS
# ==============================================================================

def test_chat_search_by_title_and_content(client, auth, dataset):
    # Create chat with distinctive title
    c_resp = client.post("/api/chats", json={
        "dataset_id": dataset,
        "title": "Inventory Optimization 2026",
    }, headers=auth)
    chat_id = c_resp.json()["chat"]["id"]

    # Search by title keyword
    s1 = client.get("/api/chats/search?q=Inventory", headers=auth)
    assert s1.status_code == 200
    found_ids = [c["id"] for c in s1.json()["chats"]]
    assert chat_id in found_ids

    # Search with unrelated query
    s2 = client.get("/api/chats/search?q=NonExistentKeywordXYZ", headers=auth)
    assert s2.status_code == 200
    assert len(s2.json()["chats"]) == 0


def test_guest_chat_isolation_from_authenticated(client, auth):
    # 1. Create a guest session
    guest = client.post("/api/auth/guest").json()
    guest_auth = {"Authorization": f"Bearer {guest['token']}"}

    # Guest loads their own sample dataset
    s_resp = client.post("/api/dataset/sample/sales_data.csv", headers=guest_auth)
    assert s_resp.status_code == 200
    guest_ds = s_resp.json()["dataset_id"]

    # Guest creates a chat
    c_guest = client.post("/api/chats", json={
        "dataset_id": guest_ds,
        "title": "Temporary Guest Chat",
    }, headers=guest_auth)
    assert c_guest.status_code == 200
    guest_chat_id = c_guest.json()["chat"]["id"]

    # Authenticated user should NOT see the guest's chat
    auth_chats = client.get("/api/chats", headers=auth).json()["chats"]
    assert all(c["id"] != guest_chat_id for c in auth_chats)

    # Guest user CAN see their own guest chat
    guest_chats = client.get("/api/chats", headers=guest_auth).json()["chats"]
    assert any(c["id"] == guest_chat_id for c in guest_chats)


# ==============================================================================
# 5. BUSINESS MEMORY TESTS
# ==============================================================================

def test_business_memory_record_and_search(client, auth, auth2):
    # Add memory for User A
    m_resp = client.post("/api/memory", json={
        "category": "pricing",
        "key": "minimum_gross_margin",
        "summary": "Minimum gross margin threshold is set at 35% across all SKUs.",
        "evidence_ref": {"kpi": "margin", "target": 0.35},
    }, headers=auth)
    assert m_resp.status_code == 200
    assert "id" in m_resp.json()

    # Search memory as User A
    search_resp = client.get("/api/memory/search?q=gross+margin", headers=auth)
    assert search_resp.status_code == 200
    results = search_resp.json()["memories"]
    assert len(results) >= 1
    assert any(r["key"] == "minimum_gross_margin" for r in results)

    # User B should NOT see User A's memory
    b_search = client.get("/api/memory/search?q=gross+margin", headers=auth2)
    assert b_search.status_code == 200
    assert len(b_search.json()["memories"]) == 0


# ==============================================================================
# 6. EXECUTIVE REPORT PERSISTENCE TESTS
# ==============================================================================

def test_report_persistence_and_isolation(client, auth, auth2, dataset):
    # User A generates an executive report
    r_gen = client.post(f"/api/reports/{dataset}/executive", headers=auth)
    assert r_gen.status_code == 200
    report_data = r_gen.json()
    assert "report_id" in report_data
    report_id = report_data["report_id"]

    # User A lists reports
    r_list = client.get("/api/reports", headers=auth)
    assert r_list.status_code == 200
    reports = r_list.json()["reports"]
    assert any(r["id"] == report_id for r in reports)

    # User A gets the saved report
    r_get = client.get(f"/api/reports/{report_id}", headers=auth)
    assert r_get.status_code == 200
    assert r_get.json()["id"] == report_id

    # User B cannot see User A's report in list
    b_list = client.get("/api/reports", headers=auth2)
    assert b_list.status_code == 200
    assert all(r["id"] != report_id for r in b_list.json()["reports"])

    # User B cannot fetch User A's report -> 404
    b_get = client.get(f"/api/reports/{report_id}", headers=auth2)
    assert b_get.status_code == 404

    # User A can delete the report
    r_del = client.delete(f"/api/reports/{report_id}", headers=auth)
    assert r_del.status_code == 200
    assert r_del.json()["ok"] is True


# ==============================================================================
# 7. GMAIL REGRESSION TESTS
# ==============================================================================

def test_gmail_preview_and_security_token_intact(client, auth, dataset):
    # Get User A's workspace
    ws_id = client.get("/api/workspaces", headers=auth).json()["active_workspace_id"]

    preview = prepare_email_preview(
        dataset_id=dataset,
        recipient="board@acmewidgets.com",
        subject="Monthly Performance Review",
        workspace_id=ws_id,
        report_type="executive",
        format_type="html",
    )
    token = preview["preview_token"]
    assert isinstance(token, str) and len(token) > 16

    # Verify preview token is stored in database
    token_row = db.one("SELECT * FROM email_preview_tokens WHERE token=?", (token,))
    assert token_row is not None
    assert token_row["recipient"] == "board@acmewidgets.com"
    assert token_row["workspace_id"] == ws_id
