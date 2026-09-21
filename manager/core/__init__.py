"""Shared business logic used by both the Flask web manager and the ssh-ws CLI.

Nothing in this package should import Flask. Keeping it framework-free is
what lets the CLI and the web UI call the exact same functions instead of
re-implementing the same rules twice.
"""
