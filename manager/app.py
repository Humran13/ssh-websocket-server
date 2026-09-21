"""SSH WebSocket Manager -- Flask application factory.

Security posture (see docs/SECURITY.md for the full review):
  * Runs as the unprivileged `sshws` service user; all root-only work goes
    through core.privileged -> scripts/priv_helper.py over sudo.
  * Session cookies: HttpOnly, SameSite=Lax, Secure when served over TLS,
    signed with a secret key generated once at install and stored with
    mode 0600 (never hard-coded, never checked into the repo).
  * CSRF protection (Flask-WTF) on every state-changing form.
  * Login is rate-limited (Flask-Limiter) to slow down credential guessing.
  * No page ever passes a raw shell string to a subprocess -- all system
    interaction goes through core/*.py, which uses argument arrays only.
"""
from __future__ import annotations

import os

from flask import Flask, redirect, session, url_for
from flask_wtf import CSRFProtect

from core import db, secret_key


def create_app(testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-only-key" if testing else secret_key.ensure()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    force_secure = os.environ.get("SSHWS_FORCE_SECURE_COOKIE", "1") == "1"
    app.config["SESSION_COOKIE_SECURE"] = force_secure and not testing
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 8  # 8 hours
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    app.config["TESTING"] = testing

    db.init_db()

    CSRFProtect(app)

    app.config["RATELIMIT_ENABLED"] = not testing
    app.config.setdefault("RATELIMIT_STORAGE_URI", "memory://")
    from rate_limit import limiter
    limiter.init_app(app)

    from routes_auth import bp as auth_bp
    from routes_dashboard import bp as dashboard_bp
    from routes_users import bp as users_bp
    from routes_settings import bp as settings_bp
    from routes_ops import bp as ops_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(ops_bp)

    @app.template_filter("fmt_ts")
    def fmt_ts(value):
        import time as _time
        if not value:
            return "-"
        return _time.strftime("%Y-%m-%d %H:%M UTC", _time.gmtime(value))

    @app.after_request
    def set_security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'"
        )
        return resp

    @app.route("/")
    def index():
        if "admin" not in session:
            return redirect(url_for("auth.login"))
        return redirect(url_for("dashboard.index"))

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8088)
