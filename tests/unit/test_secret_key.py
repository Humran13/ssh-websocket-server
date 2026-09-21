import os

from core import paths, secret_key


def test_ensure_creates_key_file_once():
    key1 = secret_key.ensure()
    key_file = paths.ETC_DIR / "secret_key"
    assert key_file.exists()
    assert len(key1) == 64  # 32 bytes hex-encoded

    key2 = secret_key.ensure()
    assert key1 == key2


def test_ensure_key_file_is_private():
    secret_key.ensure()
    key_file = paths.ETC_DIR / "secret_key"
    if os.name != "nt":
        import stat
        mode = stat.S_IMODE(key_file.stat().st_mode)
        assert mode == 0o600


def test_ensure_does_not_leave_tmp_file_behind():
    secret_key.ensure()
    tmp_file = (paths.ETC_DIR / "secret_key").with_suffix(".tmp")
    assert not tmp_file.exists()


def test_concurrent_ensure_never_disagrees():
    """Simulates the gunicorn multi-worker race for real with threads: N
    callers all start with no key file on disk and race to create it.
    Every caller must end up returning the exact same key -- this is
    exactly the bug (two gunicorn workers silently holding different
    Flask session secret keys) that core/secret_key.py's atomic
    hard-link approach exists to prevent.
    """
    import threading

    barrier = threading.Barrier(8)
    results: list[str] = []
    lock = threading.Lock()

    def worker():
        barrier.wait()  # maximize the chance every thread races together
        key = secret_key.ensure()
        with lock:
            results.append(key)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 8
    assert len(set(results)) == 1
