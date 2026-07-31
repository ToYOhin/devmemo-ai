import pytest

from app.settings import AiSettings


def test_agent_feature_flag_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AI_AGENT_ENABLED", raising=False)

    assert AiSettings.from_env().agent_enabled is False


def test_agent_feature_flag_requires_a_strict_boolean(monkeypatch):
    monkeypatch.setenv("AI_AGENT_ENABLED", "true")
    assert AiSettings.from_env().agent_enabled is True

    monkeypatch.setenv("AI_AGENT_ENABLED", "enabled")
    with pytest.raises(ValueError, match="AI_AGENT_ENABLED must be true or false"):
        AiSettings.from_env()
