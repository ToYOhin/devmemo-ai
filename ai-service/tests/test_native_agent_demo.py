from __future__ import annotations

import hashlib
import json

import pytest

from scripts.native_agent_demo import DemoError, LocalAPI, demo_environment, resolve_memos_exe, save_artifact


def test_demo_environment_replaces_inherited_live_configuration(tmp_path):
    inherited = {
        "PATH": "synthetic-path",
        "AI_PROVIDER": "deepseek",
        "AI_NOTES_DB": "real-user.db",
        "AI_AGENT_PROVIDER_MASTER_KEY": "real-key",
        "AI_AGENT_LIFECYCLE_ENABLED": "true",
        "AI_AGENT_REHYDRATION_ENABLED": "true",
        "MEMOS_OPEN_BROWSER": "true",
        "MEMOS_DATA": "real-data",
        "DEEPSEEK_API_KEY": "real-provider-key",
        "OPENAI_API_KEY": "other-key",
        "HTTP_PROXY": "http://proxy.invalid",
        "PYTHONPATH": "unrelated-modules",
    }
    before = dict(inherited)
    result = demo_environment(tmp_path, 18000, inherited)
    assert inherited == before
    assert result["PATH"] == inherited["PATH"]
    assert result["AI_PROVIDER"] == result["AI_EMBEDDING_PROVIDER"] == "deterministic"
    assert result["AI_VECTOR_STORE"] == "memory"
    assert result["AI_AGENT_LIFECYCLE_ENABLED"] == result["AI_AGENT_REHYDRATION_ENABLED"] == "false"
    assert result["AI_NOTES_DB"] == str(tmp_path / "ai-notes.db")
    assert result["AI_AGENT_INTERNAL_URL"] == "http://127.0.0.1:18000"
    assert len(result["AI_AGENT_PROVIDER_MASTER_KEY"]) == 43
    assert result["AI_AGENT_PROVIDER_MASTER_KEY"] != inherited["AI_AGENT_PROVIDER_MASTER_KEY"]
    assert result["GOMAXPROCS"] == result["OMP_NUM_THREADS"] == "1"
    for key in ("MEMOS_DATA", "MEMOS_OPEN_BROWSER", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "HTTP_PROXY"):
        assert key not in result


@pytest.mark.parametrize("name", ["DevMemoAI-0.4.0-windows-amd64-Setup.exe", "devmemo_ai_setup.exe"])
def test_launcher_rejects_installer_filenames(tmp_path, name):
    candidate = tmp_path / name
    candidate.write_bytes(b"synthetic")
    with pytest.raises(DemoError, match="portable"):
        resolve_memos_exe(candidate)


def test_launcher_requires_an_existing_binary(tmp_path):
    with pytest.raises(DemoError, match="not found"):
        resolve_memos_exe(tmp_path / "missing.exe")


@pytest.mark.parametrize("origin", ["https://example.com", "http://localhost:8000", "http://127.0.0.1:8000/path"])
def test_demo_http_client_rejects_non_loopback_origins(origin):
    with pytest.raises(DemoError, match="loopback"):
        LocalAPI(origin)


def test_report_download_checks_digest_before_writing(tmp_path):
    markdown = "# Synthetic project summary\n"
    artifact = {
        "file_name": "../../untrusted.md",
        "media_type": "text/markdown",
        "markdown": markdown,
        "digest": hashlib.sha256(markdown.encode()).hexdigest(),
    }
    report = save_artifact(tmp_path, "project-summary.md", artifact)
    assert report == tmp_path / "project-summary.md"
    assert report.read_text(encoding="utf-8") == markdown
    artifact["digest"] = "0" * 64
    with pytest.raises(DemoError, match="digest"):
        save_artifact(tmp_path, "invalid.md", artifact)
    assert not (tmp_path / "invalid.md").exists()


def test_demo_errors_do_not_dump_http_response_content(monkeypatch):
    from urllib.error import HTTPError
    from io import BytesIO

    api = LocalAPI("http://127.0.0.1:8000")
    error_body = json.dumps({"detail": "synthetic-secret-that-must-not-be-printed"}).encode()

    def fail(*_args, **_kwargs):
        raise HTTPError(api.origin, 503, "unavailable", {}, BytesIO(error_body))

    monkeypatch.setattr(api.opener, "open", fail)
    with pytest.raises(DemoError) as caught:
        api.request("GET", "/api/ai/agent/provider")
    assert "503" in str(caught.value)
    assert "synthetic-secret" not in str(caught.value)
