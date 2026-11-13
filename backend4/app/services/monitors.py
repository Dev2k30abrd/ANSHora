"""Monitors: scheduled watchers that turn data changes into money-ranked alerts."""
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from app.core import config as cfg
from app.core import db
from app.core.context import workspace_scope
from app.services import alerts as alerts_service
from app.services.dataset_manager import DatasetNotFoundError, dataset_store
from app.services.notifier import deliver
from app.services.profit_engine import analyze_profit_impact, fmt_money

log = logging.getLogger("anshora.monitors")
KINDS = ("profit_scan", "threshold", "anomaly")


def evaluate(monitor: dict) -> dict:
    """Run one monitor now. Returns {triggered, title, body, severity, impact, signature}."""
    ds = monitor["dataset_id"]
    df = dataset_store.get(ds)
    cfgm = db.loads(monitor["config"], {}) or {}
    kind = monitor["kind"]
    cur = (db.one("SELECT currency FROM workspaces WHERE id=?", (monitor["workspace_id"],)) or {}).get("currency") or cfg.DEFAULT_CURRENCY

    if kind == "threshold":
        rule = alerts_service.create_rule(cfgm["column"], cfgm["operator"], float(cfgm["threshold"]),
                                          cfgm.get("aggregation", "mean"), monitor["name"])
        hits = alerts_service.evaluate_threshold_rules(df, [rule])
        if not hits:
            return {"triggered": False}
        h = hits[0]
        return {"triggered": True, "title": f"{monitor['name']}: threshold crossed", "severity": "warning",
                "body": f"{h['column']} is {h['current_value']} ({h['operator']} {h['threshold']}).",
                "impact": None, "signature": f"thr:{h['current_value']}"}

    if kind == "anomaly":
        hits = alerts_service.evaluate_anomaly_rules(df)
        if not hits:
            return {"triggered": False}
        body = "; ".join(f"{h['column']}: {h['outlier_count']} outliers" for h in hits[:5])
        return {"triggered": True, "title": f"{monitor['name']}: anomalies detected", "severity": "warning",
                "body": body, "impact": None, "signature": "anom:" + ",".join(h["column"] for h in hits)}

    # profit_scan
    from app.services.profit_service import run_profit

    res = run_profit(ds)
    minimum = float(cfgm.get("min_impact") or 0)
    top = [f for f in res["findings"] if f["counts_toward_total"]][:3]
    if not top or res["total_at_stake"] < minimum:
        return {"triggered": False}
    sig = hashlib.md5(json.dumps([(f["id"], round(f["impact_amount"], -2)) for f in top]).encode()).hexdigest()
    body = f"Money at stake: {res['total_at_stake_formatted']}.\n" + "\n".join(
        f"{i}. {f['title']} — {f['impact_formatted']}" for i, f in enumerate(top, 1))
    sev = "critical" if res["headline"].get("revenue") and res["total_at_stake"] > 0.1 * res["headline"]["revenue"] else "warning"
    return {"triggered": True, "title": f"{monitor['name']}: {fmt_money(res['total_at_stake'], cur)} at stake",
            "severity": sev, "body": body, "impact": res["total_at_stake"], "signature": sig}


def _refresh_if_url(monitor):
    row = db.one("SELECT source FROM datasets WHERE id=?", (monitor["dataset_id"],))
    src = (row or {}).get("source") or ""
    if src.startswith("url:") and (db.loads(monitor["config"], {}) or {}).get("refresh"):
        try:
            from app.services.connectors import fetch_url_dataframe

            dataset_store.replace(monitor["dataset_id"], fetch_url_dataframe(src[4:]))
        except Exception as e:  # noqa: BLE001
            log.warning("refresh failed: %s", e)


def run_monitor(monitor_id: str, force: bool = False) -> dict:
    m = db.one("SELECT * FROM monitors WHERE id=?", (monitor_id,))
    if not m:
        raise ValueError("Monitor not found.")
    with workspace_scope(m["workspace_id"]):
        status, out = "ok", {"triggered": False}
        try:
            _refresh_if_url(m)
            out = evaluate(m)
            conf = db.loads(m["config"], {}) or {}
            if out["triggered"] and (force or conf.get("_last_sig") != out["signature"]):
                nid = db.new_id()
                db.execute(
                    "INSERT INTO notifications(id,workspace_id,monitor_id,dataset_id,title,body,severity,impact,read,created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,0,?)",
                    (nid, m["workspace_id"], m["id"], m["dataset_id"], out["title"], out["body"], out["severity"],
                     out.get("impact"), db.now()))
                out["delivery"] = deliver(db.loads(m["channels"], ["in_app"]), out["title"], out["body"], out["severity"])
                conf["_last_sig"] = out["signature"]
                db.execute("UPDATE monitors SET config=? WHERE id=?", (db.dumps(conf), m["id"]))
                out["notification_id"] = nid
            elif out["triggered"]:
                out["deduplicated"] = True
            if not out["triggered"]:
                conf = db.loads(m["config"], {}) or {}
                conf.pop("_last_sig", None)  # re-arm once the condition clears
                db.execute("UPDATE monitors SET config=? WHERE id=?", (db.dumps(conf), m["id"]))
        except DatasetNotFoundError:
            status = "dataset_missing"
        except Exception as e:  # noqa: BLE001
            status = f"error: {str(e)[:120]}"
            log.exception("monitor %s failed", monitor_id)
        db.execute("UPDATE monitors SET last_run=?, last_status=? WHERE id=?", (db.now(), status, monitor_id))
        out["status"] = status
        return out


def due_monitors() -> list[dict]:
    now = datetime.now(timezone.utc)
    due = []
    for m in db.query("SELECT * FROM monitors WHERE enabled=1"):
        if not m["last_run"]:
            due.append(m)
            continue
        try:
            last = datetime.fromisoformat(m["last_run"])
        except ValueError:
            due.append(m)
            continue
        if now - last >= timedelta(minutes=max(int(m["interval_minutes"] or 60), 1)):
            due.append(m)
    return due


_stop = threading.Event()


def _loop():
    while not _stop.is_set():
        try:
            for m in due_monitors():
                run_monitor(m["id"])
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        _stop.wait(cfg.MONITOR_TICK_SECONDS)


def start_scheduler():
    if not cfg.ENABLE_SCHEDULER:
        return
    _stop.clear()
    threading.Thread(target=_loop, daemon=True, name="anshora-scheduler").start()


def stop_scheduler():
    _stop.set()
