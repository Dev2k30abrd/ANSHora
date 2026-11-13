from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.core import db
from app.core.security import require_user
from app.services import exporter
from app.services.dataset_manager import DatasetNotFoundError

router = APIRouter(prefix="/api/export", tags=["Export"])

TYPES = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "html": "text/html; charset=utf-8", "md": "text/markdown; charset=utf-8"}


@router.get("/{dataset_id}")
def export(dataset_id: str, format: str = "pdf", user: dict = Depends(require_user)):
    if format not in TYPES:
        raise HTTPException(400, f"format must be one of {list(TYPES)}")
    try:
        payload = exporter.build_payload(dataset_id)
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))
    body = {"pdf": exporter.to_pdf, "xlsx": exporter.to_xlsx, "html": exporter.to_html, "md": exporter.to_markdown}[format](payload)
    db.audit(user["workspace_id"], user["id"], "export", f"{dataset_id}:{format}")
    return Response(body if isinstance(body, bytes) else body.encode(), media_type=TYPES[format],
                    headers={"Content-Disposition": f'attachment; filename="profit-report.{format}"'})


@router.get("/audit/log")
def audit_log(limit: int = 100, user: dict = Depends(require_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admins only.")
    return {"events": db.query("SELECT * FROM audit_log WHERE workspace_id=? ORDER BY ts DESC LIMIT ?",
                               (user["workspace_id"], min(limit, 500)))}
