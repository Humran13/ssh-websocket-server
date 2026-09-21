"""Shared Flask-Limiter instance.

Created without an app (the standard Flask-Limiter pattern) so blueprint
modules can import and decorate routes with it at import time; `create_app`
calls `limiter.init_app(app)` once the real Flask app exists. Tests disable
enforcement via `RATELIMIT_ENABLED = False` rather than skipping
initialization, so the same code path (decorated routes) runs in both
cases.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200 per minute"])
