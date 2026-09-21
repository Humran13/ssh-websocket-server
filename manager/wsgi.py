"""Gunicorn entry point: `gunicorn -w 2 -b 127.0.0.1:8088 wsgi:app` (run
with manager/ as the working directory, from the project's own venv)."""
from app import create_app

app = create_app()
