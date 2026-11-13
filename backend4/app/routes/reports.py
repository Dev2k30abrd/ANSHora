import logging
from fastapi import APIRouter, Depends, HTTPException

from app.core import db
from app.core.context import current_user_id, current_workspace
from app.core.jsonutil import jsonable
from app.core.security import require_user
from app.services.dataset_manager import dataset_store, DatasetNotFoundError
from app.services.executive_report import generate_executive_report
from app.agents.analytics_agent import ask_llm
from app.llm.client import LLMAuthError, LLMQuotaError, LLMRateLimitError, LLMTimeoutError

logger = logging.getLogger("anshora.routes.reports")

router = APIRouter(prefix="/api/reports", tags=["Executive Reports"])


@router.get("")
def list_reports(dataset_id: str | None = None, user: dict = Depends(require_user)):
    """Lists saved executive reports for the caller's workspace."""
    sql = "SELECT id, workspace_id, dataset_id, created_by, title, report_type, source, ai_warning, created_at FROM reports WHERE workspace_id=?"
    args = [user["workspace_id"]]
    if dataset_id:
        sql += " AND dataset_id=?"
        args.append(dataset_id)
    sql += " ORDER BY created_at DESC LIMIT 50"
    return {"reports": db.query(sql, tuple(args))}


@router.get("/{report_id}")
def get_report(report_id: str, user: dict = Depends(require_user)):
    """Fetches a specific saved report with full narrative and charts."""
    r = db.one("SELECT * FROM reports WHERE id=? AND workspace_id=?", (report_id, user["workspace_id"]))
    if not r:
        raise HTTPException(404, "Report not found.")
    r["data"] = db.loads(r.get("data_block"), {})
    r["charts"] = db.loads(r.get("charts"), [])
    return r


@router.delete("/{report_id}")
def delete_report(report_id: str, user: dict = Depends(require_user)):
    """Deletes a saved report."""
    r = db.one("SELECT id FROM reports WHERE id=? AND workspace_id=?", (report_id, user["workspace_id"]))
    if not r:
        raise HTTPException(404, "Report not found.")
    db.execute("DELETE FROM reports WHERE id=?", (report_id,))
    return {"ok": True}


@router.post("/{dataset_id}/executive")
def executive_report(dataset_id: str, refresh: bool = False, user: dict = Depends(require_user)):
    try:
        if not refresh:
            cached = dataset_store.get_cache(dataset_id, "executive_report")
            if cached is not None:
                return cached

        df = dataset_store.get(dataset_id)
        filename = dataset_store.get_filename(dataset_id)

        result = generate_executive_report(df, dataset_id, filename, ask_llm)
        dataset_store.set_cache(dataset_id, "executive_report", result)

        # Persist report in relational table
        rid = db.new_id()
        ws_id = user.get("workspace_id") or current_workspace.get()
        uid = user.get("id") or current_user_id.get()
        db.execute(
            "INSERT INTO reports(id,workspace_id,dataset_id,created_by,title,report_type,source,narrative,data_block,charts,ai_warning,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rid,
                ws_id,
                dataset_id,
                uid,
                f"Executive Report: {filename}",
                "executive",
                result.get("source", "ai_narrated"),
                result.get("narrative", ""),
                db.dumps(jsonable(result.get("data", {}))),
                db.dumps(jsonable(result.get("charts", []))),
                result.get("ai_warning"),
                db.now(),
            ),
        )
        result["report_id"] = rid
        return result

    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except LLMAuthError as error:
        raise HTTPException(status_code=502, detail=str(error))
    except LLMQuotaError as error:
        raise HTTPException(status_code=402, detail=str(error))
    except LLMRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error))
    except LLMTimeoutError as error:
        raise HTTPException(status_code=504, detail=str(error))
    except Exception as error:
        logger.exception("Unexpected error generating executive report for %s: %s", dataset_id, error)
        raise HTTPException(status_code=500, detail="Internal server error generating report.")
