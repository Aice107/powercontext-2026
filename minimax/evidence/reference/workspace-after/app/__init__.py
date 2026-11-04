"""TaskHub: a tiny, runnable task-management service used by the SDD demo."""

from .api import create_app

__all__ = ["create_app"]
