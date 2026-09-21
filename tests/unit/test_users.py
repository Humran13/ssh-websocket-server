import pytest

from core import db, users


@pytest.fixture(autouse=True)
def _init_db():
    db.init_db()


@pytest.fixture(autouse=True)
def _fake_privileged(monkeypatch):
    """Stub out core.privileged.call so user-lifecycle tests never touch
    a real OS account -- they exercise business rules (DB bookkeeping,
    validation, "must be managed to be modified") only.
    """
    calls = []

    def fake_call(action, args=None, timeout=40):
        calls.append((action, args or {}))
        if action == "sessions_list":
            return {"sessions": []}
        return {}

    monkeypatch.setattr(users.privileged, "call", fake_call)
    return calls


@pytest.mark.parametrize("name", ["ab", "1abc", "-abc", "ABC", "a b", "a" * 40, ""])
def test_invalid_usernames_rejected(name):
    with pytest.raises(users.UserError):
        users.validate_username(name)


@pytest.mark.parametrize("name", ["abc", "a1_2-3", "guest01"])
def test_valid_usernames_accepted(name):
    assert users.validate_username(name) == name


def test_generate_password_meets_complexity():
    for _ in range(20):
        pw = users.generate_password()
        assert len(pw) == 16
        assert any(c.islower() for c in pw)
        assert any(c.isupper() for c in pw)
        assert any(c.isdigit() for c in pw)


def test_create_user_persists_metadata(_fake_privileged):
    u = users.create_user("alice", "Password123!", actor="admin", max_sessions=2)
    assert u.username == "alice"
    assert u.max_sessions == 2
    assert u.enabled is True
    created = ("user_create", {"username": "alice", "password": "Password123!", "expires_at": None})
    assert created in _fake_privileged
    assert ("user_set_max_sessions", {"username": "alice", "max_sessions": 2}) in _fake_privileged


def test_create_duplicate_user_rejected(_fake_privileged):
    users.create_user("bob", "Password123!", actor="admin")
    with pytest.raises(users.UserError, match="already a managed user"):
        users.create_user("bob", "Password123!", actor="admin")


def test_cannot_modify_unmanaged_user():
    with pytest.raises(users.UserError, match="not a managed user"):
        users.set_password("root", "Password123!", actor="admin")
    with pytest.raises(users.UserError, match="not a managed user"):
        users.disable_user("www-data", actor="admin")
    with pytest.raises(users.UserError, match="not a managed user"):
        users.delete_user("nginx", actor="admin", confirm=True)


def test_delete_requires_confirmation(_fake_privileged):
    users.create_user("carol", "Password123!", actor="admin")
    with pytest.raises(users.UserError, match="explicit confirmation"):
        users.delete_user("carol", actor="admin", confirm=False)
    assert users.get_user("carol") is not None
    users.delete_user("carol", actor="admin", confirm=True)
    assert users.get_user("carol") is None


def test_extend_expiry_from_future_date(_fake_privileged):
    import time
    u = users.create_user("dave", "Password123!", actor="admin",
                           expires_at=int(time.time()) + 10 * 86400)
    users.extend_expiry("dave", 5 * 86400, actor="admin")
    updated = users.get_user("dave")
    assert updated.expires_at > u.expires_at


def test_remove_expiry(_fake_privileged):
    import time
    users.create_user("erin", "Password123!", actor="admin", expires_at=int(time.time()) + 86400)
    users.remove_expiry("erin", actor="admin")
    assert users.get_user("erin").expires_at is None


def test_disable_enable_roundtrip(_fake_privileged):
    users.create_user("frank", "Password123!", actor="admin")
    users.disable_user("frank", actor="admin")
    assert users.get_user("frank").enabled is False
    users.enable_user("frank", actor="admin")
    assert users.get_user("frank").enabled is True


def test_privileged_failure_does_not_create_metadata(monkeypatch):
    from core import privileged

    def failing_call(action, args=None, timeout=40):
        raise privileged.PrivilegedActionError("useradd failed")

    monkeypatch.setattr(users.privileged, "call", failing_call)
    with pytest.raises(users.UserError, match="useradd failed"):
        users.create_user("gina", "Password123!", actor="admin")
    assert users.get_user("gina") is None
