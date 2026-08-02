package aiagent

import (
	"testing"

	"github.com/stretchr/testify/require"
)

const lifecycleConfigSecret = "QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl8"

func enableLifecycleConfigEnvironment(t *testing.T) {
	t.Helper()
	t.Setenv("AI_AGENT_ENABLED", "true")
	t.Setenv("AI_AGENT_INTERNAL_URL", "http://ai-service:8000")
	t.Setenv("AI_AGENT_INTERNAL_SECRET", "delegation-secret")
	t.Setenv("AI_AGENT_REHYDRATION_ENABLED", "true")
	t.Setenv("AI_AGENT_REHYDRATION_SECRET_CURRENT", testEvidenceRehydrationCurrentSecret)
	t.Setenv("AI_AGENT_REHYDRATION_SECRET_PREVIOUS", "")
	t.Setenv("AI_AGENT_LIFECYCLE_ENABLED", "true")
	t.Setenv("AI_AGENT_LIFECYCLE_SECRET", lifecycleConfigSecret)
	t.Setenv("AI_AGENT_LIFECYCLE_GENERATION", "r5-disposable-1")
}

func TestLifecycleRuntimeConfigIsDisabledAndSecretFreeByDefault(t *testing.T) {
	t.Setenv("AI_AGENT_LIFECYCLE_ENABLED", "false")
	t.Setenv("AI_AGENT_LIFECYCLE_SECRET", lifecycleConfigSecret)

	config, err := LoadLifecycleRuntimeConfigFromEnv()

	require.NoError(t, err)
	require.Equal(t, LifecycleRuntimeConfig{}, config)
}

func TestLifecycleRuntimeConfigAcceptsStrictSingleHostOptIn(t *testing.T) {
	enableLifecycleConfigEnvironment(t)

	config, err := LoadLifecycleRuntimeConfigFromEnv()

	require.NoError(t, err)
	require.Equal(t, "http://ai-service:8000", config.InternalURL)
	require.Equal(t, lifecycleConfigSecret, config.Secret)
	require.Equal(t, "r5-disposable-1", config.Generation)
}

func TestLifecycleRuntimeConfigRejectsUnsafeSelections(t *testing.T) {
	tests := []struct {
		name  string
		env   string
		value string
	}{
		{"invalid flag", "AI_AGENT_LIFECYCLE_ENABLED", "enabled"},
		{"rehydration disabled", "AI_AGENT_REHYDRATION_ENABLED", "false"},
		{"credential URL", "AI_AGENT_INTERNAL_URL", "http://user:pass@ai-service:8000"},
		{"URL path", "AI_AGENT_INTERNAL_URL", "http://ai-service:8000/path"},
		{"short secret", "AI_AGENT_LIFECYCLE_SECRET", "short"},
		{"shared delegation secret", "AI_AGENT_INTERNAL_SECRET", lifecycleConfigSecret},
		{"shared rehydration secret", "AI_AGENT_LIFECYCLE_SECRET", testEvidenceRehydrationCurrentSecret},
		{"invalid generation", "AI_AGENT_LIFECYCLE_GENERATION", "contains spaces"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			enableLifecycleConfigEnvironment(t)
			t.Setenv(test.env, test.value)

			_, err := LoadLifecycleRuntimeConfigFromEnv()

			require.ErrorIs(t, err, ErrInvalidLifecycleRuntimeConfig)
		})
	}
}
