import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from app.agents.agent import run_agent_stream
from app.core import db
from app.core.jsonutil import jsonable
from app.core.security import require_user
from app.routes.agent import project_for, sse
from app.services.dataset_manager import DatasetNotFoundError

router = APIRouter(prefix="/api/chats", tags=["Chats"])


def _own_chat(chat_id, user):
    c = db.one("SELECT * FROM chats WHERE id=? AND workspace_id=?", (chat_id, user["workspace_id"]))
    if not c:
        raise HTTPException(404, "Chat not found.")
    return c


class NewChat(BaseModel):
    dataset_id: str | None = None
    title: str | None = None
    project_id: str | None = None


class Rename(BaseModel):
    title: str | None = None
    dataset_id: str | None = None


class StreamBody(BaseModel):
    question: str | None = None
    regenerate: bool = False
    edit_message_id: str | None = None


@router.get("")
def list_chats(
    dataset_id: str | None = None,
    project_id: str | None = None,
    q: str | None = None,
    user: dict = Depends(require_user),
):
    sql = "SELECT * FROM chats WHERE workspace_id=?"
    args = [user["workspace_id"]]

    # Non-guest users only see their persistent chats; guest sees only current session's chats
    is_guest = user.get("role") == "guest" or user.get("email", "").startswith("guest_")
    if not is_guest:
        sql += " AND (is_guest IS NULL OR is_guest=0)"
    else:
        sql += " AND is_guest=1 AND user_id=?"
        args.append(user["id"])

    if dataset_id:
        sql += " AND dataset_id=?"
        args.append(dataset_id)
    if project_id:
        sql += " AND project_id=?"
        args.append(project_id)
    if q and q.strip():
        sql += " AND title LIKE ?"
        args.append(f"%{q.strip()}%")

    sql += " ORDER BY updated_at DESC LIMIT 200"
    return {"chats": db.query(sql, tuple(args))}


@router.get("/search")
def search_chats(q: str, user: dict = Depends(require_user)):
    """Searches conversations by title and message content."""
    is_guest = user.get("role") == "guest" or user.get("email", "").startswith("guest_")
    if is_guest:
        return {"chats": []}
    term = f"%{q.strip()}%"
    chats = db.query(
        "SELECT DISTINCT c.* FROM chats c "
        "LEFT JOIN messages m ON m.chat_id = c.id "
        "WHERE c.workspace_id=? AND (c.is_guest IS NULL OR c.is_guest=0) "
        "AND (c.title LIKE ? OR m.content LIKE ?) "
        "ORDER BY c.updated_at DESC LIMIT 50",
        (user["workspace_id"], term, term),
    )
    return {"chats": chats}


@router.post("")
def create_chat(b: NewChat, user: dict = Depends(require_user)):
    from app.services.dataset_manager import dataset_store

    if b.dataset_id:
        try:
            dataset_store.get(b.dataset_id)
        except DatasetNotFoundError as e:
            raise HTTPException(404, str(e))
    cid, now = db.new_id(), db.now()
    is_guest = 1 if (user.get("role") == "guest" or user.get("email", "").startswith("guest_")) else 0

    db.execute(
        "INSERT INTO chats(id,workspace_id,user_id,project_id,dataset_id,title,is_guest,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (cid, user["workspace_id"], user["id"], b.project_id, b.dataset_id, b.title or "New chat", is_guest, now, now),
    )
    return {"chat": db.one("SELECT * FROM chats WHERE id=?", (cid,))}


@router.get("/{chat_id}")
def get_chat(chat_id: str, user: dict = Depends(require_user)):
    c = _own_chat(chat_id, user)
    c["pending_action"] = db.loads(c.get("pending_action"))
    msgs = db.query("SELECT * FROM messages WHERE chat_id=? ORDER BY created_at, rowid", (chat_id,))
    for m in msgs:
        m["meta"] = db.loads(m["meta"], {})
    return {"chat": c, "messages": msgs}


@router.patch("/{chat_id}")
def rename(chat_id: str, b: Rename, user: dict = Depends(require_user)):
    _own_chat(chat_id, user)
    updates = []
    args = []
    if b.title is not None and b.title.strip():
        updates.append("title=?")
        args.append(b.title.strip()[:120])
    if b.dataset_id is not None:
        from app.services.dataset_manager import dataset_store
        if b.dataset_id:
            try:
                dataset_store.get(b.dataset_id)
            except DatasetNotFoundError as e:
                raise HTTPException(404, str(e))
        updates.append("dataset_id=?")
        args.append(b.dataset_id or None)
    if updates:
        updates.append("updated_at=?")
        args.append(db.now())
        args.append(chat_id)
        db.execute(f"UPDATE chats SET {', '.join(updates)} WHERE id=?", tuple(args))
    return {"ok": True, "chat": db.one("SELECT * FROM chats WHERE id=?", (chat_id,))}


@router.delete("/{chat_id}")
def delete_chat(chat_id: str, user: dict = Depends(require_user)):
    _own_chat(chat_id, user)
    db.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
    db.execute("DELETE FROM chats WHERE id=?", (chat_id,))
    return {"ok": True}


@router.get("/{chat_id}/export", response_class=PlainTextResponse)
def export_chat(chat_id: str, user: dict = Depends(require_user)):
    c = _own_chat(chat_id, user)
    out = [f"# {c['title']}", ""]
    for m in db.query("SELECT * FROM messages WHERE chat_id=? ORDER BY created_at, rowid", (chat_id,)):
        out += [f"**{'You' if m['role'] == 'user' else 'Anshora'}:** {m['content']}", ""]
    return PlainTextResponse("\n".join(out), headers={"Content-Disposition": f'attachment; filename="chat-{chat_id[:8]}.md"'})


def _slim_meta(done: dict) -> dict:
    runs = []
    for r in done.get("tool_runs", []):
        res = r.get("result")
        keep = res if res is not None and len(json.dumps(res, default=str)) < 120_000 else None
        runs.append({**{k: v for k, v in r.items() if k != "result"}, "result": keep})
    return {"tool_runs": runs, "verification": done.get("verification"), "confidence": done.get("confidence"),
            "followups": done.get("followups"), "mode": done.get("mode"), "demo": done.get("demo"),
            "elapsed_ms": done.get("elapsed_ms"), "pending_action": done.get("pending_action"),
            "email_preview": done.get("email_preview")}


@router.post("/{chat_id}/stream")
def stream(chat_id: str, b: StreamBody, user: dict = Depends(require_user)):
    chat = _own_chat(chat_id, user)
    pending_action = db.loads(chat.get("pending_action"))
    msgs = db.query("SELECT * FROM messages WHERE chat_id=? ORDER BY created_at, rowid", (chat_id,))

    # resolve what to run: edit / regenerate / new question
    if b.edit_message_id:
        idx = next((i for i, m in enumerate(msgs) if m["id"] == b.edit_message_id and m["role"] == "user"), None)
        if idx is None or not (b.question or "").strip():
            raise HTTPException(400, "Cannot edit that message.")
        for m in msgs[idx:]:
            db.execute("DELETE FROM messages WHERE id=?", (m["id"],))
        msgs, question = msgs[:idx], b.question.strip()
    elif b.regenerate:
        while msgs and msgs[-1]["role"] == "assistant":
            db.execute("DELETE FROM messages WHERE id=?", (msgs.pop()["id"],))
        last_user = next((m for m in reversed(msgs) if m["role"] == "user"), None)
        if not last_user:
            raise HTTPException(400, "Nothing to regenerate.")
        db.execute("DELETE FROM messages WHERE id=?", (last_user["id"],))
        msgs, question = msgs[:-1], last_user["content"]
    else:
        question = (b.question or "").strip()
        if not question:
            raise HTTPException(400, "Question is empty.")

    history = [{"role": m["role"], "content": m["content"]} for m in msgs]
    uid = db.new_id()
    db.execute("INSERT INTO messages(id,chat_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?)",
               (uid, chat_id, "user", question, "{}", db.now()))
    if chat["title"] == "New chat" or not msgs:
        db.execute("UPDATE chats SET title=? WHERE id=?", (question[:60], chat_id))
    try:
        proj = project_for(chat["dataset_id"])
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))

    def gen():
        partial, saved = "", False
        yield sse({"type": "meta", "chat_id": chat_id, "user_message_id": uid})
        try:
            for ev in run_agent_stream(question, chat["dataset_id"], history, proj, pending_action=pending_action):
                if ev["type"] == "chunk":
                    partial += ev["text"]
                elif ev["type"] == "retract":
                    partial = ""
                elif ev["type"] == "done":
                    aid = db.new_id()
                    new_pending = ev.get("pending_action")
                    db.execute("INSERT INTO messages(id,chat_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?)",
                               (aid, chat_id, "assistant", ev["answer"], db.dumps(jsonable(_slim_meta(ev))), db.now()))
                    db.execute("UPDATE chats SET pending_action=?, updated_at=? WHERE id=?",
                               (db.dumps(new_pending) if new_pending else None, db.now(), chat_id))
                    saved = True
                    ev = {**ev, "message_id": aid}
                yield sse(ev)
        except GeneratorExit:
            raise
        except Exception as e:  # noqa: BLE001
            yield sse({"type": "error", "message": str(e)})
        finally:
            if not saved and partial.strip():
                db.execute("INSERT INTO messages(id,chat_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?)",
                           (db.new_id(), chat_id, "assistant", partial, db.dumps({"stopped": True}), db.now()))
                db.execute("UPDATE chats SET updated_at=? WHERE id=?", (db.now(), chat_id))

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
