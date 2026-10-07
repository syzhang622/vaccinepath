"""Agent setup must bind every run to the least-privilege custom profile."""

from pathlib import Path

from vaccinepath.agent import setup


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


def test_profile_is_a_deny_by_default_allowlist():
    profile = Path(setup.__file__).parent / "profile" / "config.yaml"
    text = profile.read_text()
    assert "tool_groups:\n  - vaccinepath" in text
    assert "skills: []" in text
    assert "mcp_plugins: []" in text
    assert "allowed_subagents: []" in text
    assert "memory_enabled: false" in text
    assert all(name not in text for name in ("web", "bash", "file:read", "file:write", "browser"))


def test_setup_binds_thread_and_schedule_to_custom_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("VACCINEPATH_DATA_DIR", str(tmp_path))
    calls = []

    def post(url, *, json, headers, timeout):
        calls.append((url, json))
        return FakeResponse({"thread_id": "thread-1"} if url.endswith("/api/threads") else {"id": "scheduled-1"})

    monkeypatch.setattr(setup.requests, "post", post)
    monkeypatch.setattr(setup.requests, "put", lambda *args, **kwargs: FakeResponse({}))
    cfg = setup.setup_agent(base="http://gateway.test")

    assert calls[0][1]["assistant_id"] == "vaccinepath"
    assert calls[1][1]["assistant_id"] == "vaccinepath"
    assert cfg["assistant_id"] == "vaccinepath"
