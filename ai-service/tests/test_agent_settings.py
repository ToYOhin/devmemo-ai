import pytest

from app.settings import AiSettings


CURRENT_REHYDRATION_SECRET = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"
PREVIOUS_REHYDRATION_SECRET = "ICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj8"
LIFECYCLE_SECRET = "QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl8"


def test_agent_feature_flag_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AI_AGENT_ENABLED", raising=False)

    assert AiSettings.from_env().agent_enabled is False


def test_agent_feature_flag_requires_a_strict_boolean(monkeypatch):
    monkeypatch.setenv("AI_AGENT_ENABLED", "true")
    monkeypatch.setenv("AI_AGENT_INTERNAL_SECRET", "agent-only-test-secret")
    assert AiSettings.from_env().agent_enabled is True

    monkeypatch.setenv("AI_AGENT_ENABLED", "enabled")
    with pytest.raises(ValueError, match="AI_AGENT_ENABLED must be true or false"):
        AiSettings.from_env()


def test_enabled_agent_requires_a_distinct_internal_delegation_secret(monkeypatch):
    monkeypatch.setenv("AI_AGENT_ENABLED", "true")
    monkeypatch.delenv("AI_AGENT_INTERNAL_SECRET", raising=False)

    with pytest.raises(ValueError, match="AI_AGENT_INTERNAL_SECRET is required"):
        AiSettings.from_env()

    monkeypatch.setenv("AI_AGENT_INTERNAL_SECRET", "agent-only-test-secret")
    assert AiSettings.from_env().agent_internal_secret == "agent-only-test-secret"


def test_rehydration_runtime_is_disabled_and_secret_free_by_default(monkeypatch):
    monkeypatch.delenv("AI_AGENT_REHYDRATION_ENABLED", raising=False)
    monkeypatch.setenv(
        "AI_AGENT_REHYDRATION_SECRET_CURRENT", CURRENT_REHYDRATION_SECRET
    )

    settings = AiSettings.from_env()

    assert settings.agent_rehydration_enabled is False
    assert settings.agent_rehydration_secret_current is None
    assert settings.agent_rehydration_secret_previous is None
    assert settings.agent_rehydration_memos_url is None


def test_rehydration_runtime_accepts_distinct_keyring_and_single_origin(monkeypatch):
    monkeypatch.setenv("AI_AGENT_ENABLED", "true")
    monkeypatch.setenv("AI_AGENT_INTERNAL_SECRET", "separate-delegation-secret")
    monkeypatch.setenv("AI_AGENT_REHYDRATION_ENABLED", "true")
    monkeypatch.setenv(
        "AI_AGENT_REHYDRATION_SECRET_CURRENT", CURRENT_REHYDRATION_SECRET
    )
    monkeypatch.setenv(
        "AI_AGENT_REHYDRATION_SECRET_PREVIOUS", PREVIOUS_REHYDRATION_SECRET
    )
    monkeypatch.setenv(
        "AI_AGENT_REHYDRATION_MEMOS_URL", "http://memos.internal:5230/"
    )

    settings = AiSettings.from_env()

    assert settings.agent_rehydration_enabled is True
    assert settings.agent_rehydration_secret_current == CURRENT_REHYDRATION_SECRET
    assert settings.agent_rehydration_secret_previous == PREVIOUS_REHYDRATION_SECRET
    assert settings.agent_rehydration_memos_url == "http://memos.internal:5230"


@pytest.mark.parametrize(
    ("environment", "error"),
    [
        (
            {"AI_AGENT_ENABLED": "false"},
            "AI_AGENT_REHYDRATION_ENABLED requires AI_AGENT_ENABLED=true",
        ),
        (
            {"AI_AGENT_REHYDRATION_SECRET_CURRENT": "short"},
            "AI_AGENT_REHYDRATION_SECRET_CURRENT must be",
        ),
        (
            {
                "AI_AGENT_REHYDRATION_SECRET_PREVIOUS": CURRENT_REHYDRATION_SECRET,
            },
            "current and previous secrets must differ",
        ),
        (
            {"AI_AGENT_INTERNAL_SECRET": CURRENT_REHYDRATION_SECRET},
            "rehydration secrets must differ from delegation secret",
        ),
        (
            {"AI_AGENT_REHYDRATION_MEMOS_URL": "http://user:pass@memos/path"},
            "AI_AGENT_REHYDRATION_MEMOS_URL must be one HTTP",
        ),
        (
            {"AI_AGENT_REHYDRATION_MEMOS_URL": "http://memos.internal:invalid"},
            "AI_AGENT_REHYDRATION_MEMOS_URL must be one HTTP",
        ),
    ],
)
def test_rehydration_runtime_rejects_unsafe_enablement(monkeypatch, environment, error):
    monkeypatch.setenv("AI_AGENT_ENABLED", "true")
    monkeypatch.setenv("AI_AGENT_INTERNAL_SECRET", "separate-delegation-secret")
    monkeypatch.setenv("AI_AGENT_REHYDRATION_ENABLED", "true")
    monkeypatch.setenv(
        "AI_AGENT_REHYDRATION_SECRET_CURRENT", CURRENT_REHYDRATION_SECRET
    )
    monkeypatch.delenv("AI_AGENT_REHYDRATION_SECRET_PREVIOUS", raising=False)
    monkeypatch.setenv("AI_AGENT_REHYDRATION_MEMOS_URL", "http://memos.internal:5230")
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=error):
        AiSettings.from_env()


def _enable_rehydration(monkeypatch):
    monkeypatch.setenv("AI_AGENT_ENABLED", "true")
    monkeypatch.setenv("AI_AGENT_INTERNAL_SECRET", "separate-delegation-secret")
    monkeypatch.setenv("AI_AGENT_REHYDRATION_ENABLED", "true")
    monkeypatch.setenv(
        "AI_AGENT_REHYDRATION_SECRET_CURRENT", CURRENT_REHYDRATION_SECRET
    )
    monkeypatch.setenv("AI_AGENT_REHYDRATION_MEMOS_URL", "http://memos:5230")


def test_lifecycle_runtime_is_disabled_and_secret_free_by_default(monkeypatch):
    monkeypatch.delenv("AI_AGENT_LIFECYCLE_ENABLED", raising=False)
    monkeypatch.setenv("AI_AGENT_LIFECYCLE_SECRET", LIFECYCLE_SECRET)

    settings = AiSettings.from_env()

    assert settings.agent_lifecycle_enabled is False
    assert settings.agent_lifecycle_secret is None
    assert settings.agent_lifecycle_generation is None


def test_lifecycle_runtime_accepts_strict_single_host_qdrant_opt_in(monkeypatch):
    _enable_rehydration(monkeypatch)
    monkeypatch.setenv("AI_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("AI_AGENT_LIFECYCLE_ENABLED", "true")
    monkeypatch.setenv("AI_AGENT_LIFECYCLE_SECRET", LIFECYCLE_SECRET)
    monkeypatch.setenv("AI_AGENT_LIFECYCLE_GENERATION", "r5-disposable-1")

    settings = AiSettings.from_env()

    assert settings.agent_lifecycle_enabled is True
    assert settings.agent_lifecycle_secret == LIFECYCLE_SECRET
    assert settings.agent_lifecycle_generation == "r5-disposable-1"


@pytest.mark.parametrize(
    ("environment", "error"),
    [
        (
            {"AI_AGENT_REHYDRATION_ENABLED": "false"},
            "requires AI_AGENT_REHYDRATION_ENABLED=true",
        ),
        ({"AI_VECTOR_STORE": "memory"}, "requires memo-mode Qdrant"),
        ({"AI_INDEX_MODE": "chunk"}, "requires memo-mode Qdrant"),
        ({"AI_AGENT_LIFECYCLE_SECRET": "short"}, "must be an unpadded"),
        (
            {"AI_AGENT_LIFECYCLE_SECRET": CURRENT_REHYDRATION_SECRET},
            "must differ from Agent runtime secrets",
        ),
        ({"AI_AGENT_LIFECYCLE_GENERATION": "contains spaces"}, "bounded opaque"),
    ],
)
def test_lifecycle_runtime_rejects_unsafe_enablement(
    monkeypatch, environment, error
):
    _enable_rehydration(monkeypatch)
    monkeypatch.setenv("AI_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("AI_AGENT_LIFECYCLE_ENABLED", "true")
    monkeypatch.setenv("AI_AGENT_LIFECYCLE_SECRET", LIFECYCLE_SECRET)
    monkeypatch.setenv("AI_AGENT_LIFECYCLE_GENERATION", "r5-disposable-1")
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=error):
        AiSettings.from_env()
