import pytest

from core import auth, db


@pytest.fixture(autouse=True)
def _init_db():
    db.init_db()


def test_no_admin_initially():
    assert auth.has_any_admin() is False


def test_create_admin_and_login():
    auth.create_admin("admin", "supersecretpassword")
    assert auth.has_any_admin() is True
    assert auth.verify_login("admin", "supersecretpassword") is True
    assert auth.verify_login("admin", "wrongpassword") is False
    assert auth.verify_login("nosuchuser", "whatever12345") is False


def test_password_never_stored_in_plaintext():
    auth.create_admin("admin", "supersecretpassword")
    with db.cursor() as cur:
        cur.execute("SELECT password_hash FROM admin_users WHERE username = 'admin'")
        row = cur.fetchone()
    assert "supersecretpassword" not in row["password_hash"]


def test_short_password_rejected():
    with pytest.raises(auth.AuthError):
        auth.create_admin("admin", "short")


def test_short_username_rejected():
    with pytest.raises(auth.AuthError):
        auth.create_admin("ab", "supersecretpassword")


def test_change_password():
    auth.create_admin("admin", "originalpassword1")
    auth.change_password("admin", "newpassword12345")
    assert auth.verify_login("admin", "newpassword12345") is True
    assert auth.verify_login("admin", "originalpassword1") is False
