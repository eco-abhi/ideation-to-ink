from engine.tools import cache


def test_cache_miss_then_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return {"x": 1}

    first = cache.cached_get("src", "endpoint", {"q": "a"}, fetch)
    second = cache.cached_get("src", "endpoint", {"q": "a"}, fetch)

    assert first == {"x": 1}
    assert second == {"x": 1}
    assert len(calls) == 1  # second call served from disk, fetch not invoked again


def test_cache_expired_refetches(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return {"n": len(calls)}

    cache.cached_get("src", "endpoint", {"q": "a"}, fetch, ttl_days=0)
    import time

    time.sleep(0.01)
    cache.cached_get("src", "endpoint", {"q": "a"}, fetch, ttl_days=0)

    assert len(calls) == 2


def test_different_params_are_different_cache_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path)
    cache.cached_get("src", "endpoint", {"q": "a"}, lambda: {"v": "a"})
    cache.cached_get("src", "endpoint", {"q": "b"}, lambda: {"v": "b"})
    files = list((tmp_path / "src").glob("*.json"))
    assert len(files) == 2
