# Anshora Analyst — Backend (FastAPI)

Verified AI data analyst. Upload data → ask questions → get answers **with proof, a confidence score and the money at stake**.

## Quick Local Startup (Windows PowerShell)

```powershell
cd backend4
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/docs` for the interactive OpenAPI documentation. Health check: `http://127.0.0.1:8000/health`.

---

## Phase 2 Architecture: PostgreSQL, Multi-Tenancy & Google Sign-In

### 1. Dual Database Engine (PostgreSQL / SQLite Fallback)
Anshora supports dual database operation through SQLAlchemy 2.0 and standard SQL queries:
- **Local Development**: When `DATABASE_URL` is empty, Anshora automatically runs with SQLite at `data/anshora.db`. Zero setup required.
- **Production PostgreSQL**: Set `DATABASE_URL` in `.env`:
  ```bash
  DATABASE_URL=postgresql+psycopg2://anshora_user:strong_password@localhost:5432/anshora
  ```
- **Alembic Migrations**:
  ```bash
  # Check current revision
  alembic current

  # Apply all migrations to database
  alembic upgrade head
  ```
- **Safe SQLite-to-PostgreSQL Data Migration**:
  A non-destructive migration script migrates existing SQLite tables, users, workspaces, datasets, chats, messages, decisions, and Gmail integrations:
  ```bash
  python scripts/migrate_sqlite_to_pg.py
  ```
  *(Creates a timestamped backup before migration, e.g., `anshora.db.bak_YYYYMMDD_HHMMSS`)*.

---

### 2. Google OAuth 2.0 Sign-In vs. Gmail Delivery Separation
To prevent credential mixing and privilege creep, Anshora maintains two separate OAuth flows:

| Capability | OAuth Purpose | Scopes | Storage | Callback Endpoint |
|---|---|---|---|---|
| **User Sign-In** | Authentication & Identity | `openid`, `email`, `profile` | `users`, `oauth_identities` | `/api/auth/google/callback` |
| **Gmail Delivery** | Sending Verified Reports | `gmail.send` | `gmail_integrations` | `/api/gmail/oauth/callback` |

Configure both in `.env`:
```ini
# Google Sign-In (User Auth)
GOOGLE_SIGNIN_CLIENT_ID=your-google-oauth-client-id.apps.googleusercontent.com
GOOGLE_SIGNIN_CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_SIGNIN_REDIRECT_URI=http://localhost:8000/api/auth/google/callback

# Gmail Delivery (Sending Reports via anshora.ai.agent@gmail.com)
GOOGLE_CLIENT_ID=your-gmail-oauth-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-gmail-oauth-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/gmail/oauth/callback
```

---

### 3. Multi-Tenant Isolation & Security Guards
Every analytical asset is strictly tenant-scoped to the active user's `workspace_id`:
- **Workspaces**: Users can create, rename, and switch workspaces (`/api/workspaces`). Users cannot delete their sole workspace.
- **Cross-Tenant IDOR Prevention**: Authorization dependencies in `app/core/tenancy.py` enforce ownership before executing queries against datasets, chats, projects, decisions, or reports.
- **Guest Ephemerality**: Guests receive temporary isolated workspaces. Guest conversations are marked `is_guest=1` and hidden from authenticated conversation histories.
- **Persistent Reports**: Executive reports are persisted to the relational database (`reports` table) with audit trail.
- **Business Memory Engine**: Organizational facts, thresholds, and decisions sync to the `business_memory` table and are queryable via `/api/memory`.

---

## Running the Automated Test Suite

Run all 73 backend unit and integration tests:

```bash
# Run full suite
pytest backend4/tests -v

# Run Phase 2 Security & Auth tests
pytest backend4/tests/test_phase2_security_and_auth.py -v
```

All 73 tests cover:
- Numerical accuracy benchmarks & ground truth verification
- Multi-step agent loop & resilient tool calling
- Conversational Gmail delivery & preview token confirmation
- LLM error recovery (HTTP 503 resilience, deterministic fallback)
- Google Sign-In, ID token claim verification & existing account linking
- Cross-tenant data isolation & IDOR prevention
- Business memory recording and search
- Workspace lifecycle management
