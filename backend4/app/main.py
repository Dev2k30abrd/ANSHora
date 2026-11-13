import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import config as cfg
from app.core import db
from app.core.security import require_user
from app.routes import (agent, alerts, analytics, auth, chats, dashboard, dataset, decisions, export, forecast,
                        gmail, insights, memory, monitors, profit, projects, reports, root_cause, semantic, system, whatif, workspaces)
from app.services.monitors import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    start_scheduler()
    if cfg.use_mock_llm():
        logging.getLogger("anshora").warning("No LLM key configured — running in DEMO mode (offline brain).")
    yield
    stop_scheduler()


app = FastAPI(title="Anshora Analyst API", version="1.0.0",
              description="Verified AI data analyst: money-first insights with proof.", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=cfg.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# public
app.include_router(system.router)
app.include_router(auth.router)
app.include_router(gmail.router)

# everything else requires a signed-in user (tenant-scoped through the workspace context)
protected = [dataset.router, analytics.router, agent.router, dashboard.router, insights.router, root_cause.router,
             forecast.router, whatif.router, alerts.router, reports.router, semantic.router, chats.router,
             projects.router, profit.router, decisions.router, monitors.router, export.router,
             workspaces.router, memory.router]
for r in protected:
    app.include_router(r, dependencies=[Depends(require_user)])


@app.get("/")
def root():
    return {"message": "Anshora Analyst API is running", "version": "1.0.0", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "healthy"}
