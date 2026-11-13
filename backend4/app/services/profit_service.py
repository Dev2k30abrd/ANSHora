"""Dataset-aware wrappers so every caller (agent, REST, monitors, exports) gets identical numbers."""
from app.core import config as cfg
from app.core import db
from app.core.context import current_workspace
from app.services.dataset_manager import dataset_store
from app.services.profit_engine import analyze_profit_impact, sensitivity_analysis


def currency_for(dataset_id: str) -> str:
    meta = db.one("SELECT project_id, workspace_id FROM datasets WHERE id=?", (dataset_id,))
    if meta and meta.get("project_id"):
        p = db.one("SELECT currency FROM projects WHERE id=?", (meta["project_id"],))
        if p and p.get("currency"):
            return p["currency"]
    ws = (meta or {}).get("workspace_id") or current_workspace.get()
    row = db.one("SELECT currency FROM workspaces WHERE id=?", (ws,)) if ws else None
    return (row or {}).get("currency") or cfg.DEFAULT_CURRENCY


def run_profit(dataset_id: str) -> dict:
    return analyze_profit_impact(
        dataset_store.get(dataset_id), dataset_store.get_pack_id(dataset_id),
        dataset_store.get_business_context(dataset_id), currency_for(dataset_id),
        raw_df=dataset_store.get_raw(dataset_id))


def run_sensitivity(dataset_id: str, **kw) -> dict:
    return sensitivity_analysis(
        dataset_store.get(dataset_id), dataset_store.get_pack_id(dataset_id),
        dataset_store.get_business_context(dataset_id), currency_for(dataset_id), **kw)
