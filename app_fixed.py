"""Railway/Procfile compatibility entry point.

The application is fully implemented in app.py. Keeping this module allows old
Railway start commands that still reference ``app_fixed:app`` to continue
working without overriding the current routes.
"""

from app import app

__all__ = ["app"]
