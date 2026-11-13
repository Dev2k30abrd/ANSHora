"""Per-request workspace context so the dataset store enforces tenant isolation."""
from contextlib import contextmanager
from contextvars import ContextVar

current_workspace: ContextVar = ContextVar("current_workspace", default=None)
current_user_id: ContextVar = ContextVar("current_user_id", default=None)


@contextmanager
def workspace_scope(workspace_id):
    """Run code as a workspace (None = system/internal, no restriction)."""
    t = current_workspace.set(workspace_id)
    try:
        yield
    finally:
        current_workspace.reset(t)
