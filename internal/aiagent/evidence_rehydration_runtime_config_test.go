package aiagent

import (
	"testing"

	"github.com/stretchr/testify/require"
)

const (
	testEvidenceRehydrationCurrentSecret  = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"
	testEvidenceRehydrationPreviousSecret = "ICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj8"
)

func TestEvidenceRehydrationRuntimeConfigIsDisabledAndSecretFreeByDefault(t *testing.T) {
	t.Setenv(evidenceRehydrationEnabledEnv, "")
	t.Setenv(evidenceRehydrationCurrentSecretEnv, testEvidenceRehydrationCurrentSecret)
	t.Setenv(evidenceRehydrationPreviousSecretEnv, testEvidenceRehydrationPreviousSecret)

	config, err := LoadEvidenceRehydrationRuntimeConfigFromEnv()

	require.NoError(t, err)
	require.Equal(t, EvidenceRehydrationRuntimeConfig{}, config)
}

func TestEvidenceRehydrationRuntimeConfigAcceptsDistinctCurrentAndPreviousSecrets(t *testing.T) {
	t.Setenv("AI_AGENT_ENABLED", "true")
	t.Setenv("AI_AGENT_INTERNAL_SECRET", "separate-delegation-secret")
	t.Setenv(evidenceRehydrationEnabledEnv, "true")
	t.Setenv(evidenceRehydrationCurrentSecretEnv, testEvidenceRehydrationCurrentSecret)
	t.Setenv(evidenceRehydrationPreviousSecretEnv, testEvidenceRehydrationPreviousSecret)

	config, err := LoadEvidenceRehydrationRuntimeConfigFromEnv()

	require.NoError(t, err)
	require.True(t, config.Enabled)
	require.Equal(t, testEvidenceRehydrationCurrentSecret, config.CurrentSecret)
	require.Equal(t, testEvidenceRehydrationPreviousSecret, config.PreviousSecret)
}

func TestEvidenceRehydrationRuntimeConfigRejectsUnsafeEnablement(t *testing.T) {
	tests := []struct {
		name               string
		agentEnabled       string
		rehydrationEnabled string
		current            string
		previous           string
		delegation         string
	}{
		{name: "invalid flag", agentEnabled: "true", rehydrationEnabled: "enabled", current: testEvidenceRehydrationCurrentSecret},
		{name: "agent disabled", rehydrationEnabled: "true", current: testEvidenceRehydrationCurrentSecret},
		{name: "missing current", agentEnabled: "true", rehydrationEnabled: "true"},
		{name: "invalid current", agentEnabled: "true", rehydrationEnabled: "true", current: "short"},
		{name: "invalid previous", agentEnabled: "true", rehydrationEnabled: "true", current: testEvidenceRehydrationCurrentSecret, previous: "short"},
		{name: "duplicate keys", agentEnabled: "true", rehydrationEnabled: "true", current: testEvidenceRehydrationCurrentSecret, previous: testEvidenceRehydrationCurrentSecret},
		{name: "current reuses delegation", agentEnabled: "true", rehydrationEnabled: "true", current: testEvidenceRehydrationCurrentSecret, delegation: testEvidenceRehydrationCurrentSecret},
		{name: "previous reuses delegation", agentEnabled: "true", rehydrationEnabled: "true", current: testEvidenceRehydrationCurrentSecret, previous: testEvidenceRehydrationPreviousSecret, delegation: testEvidenceRehydrationPreviousSecret},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Setenv("AI_AGENT_ENABLED", test.agentEnabled)
			t.Setenv("AI_AGENT_INTERNAL_SECRET", test.delegation)
			t.Setenv(evidenceRehydrationEnabledEnv, test.rehydrationEnabled)
			t.Setenv(evidenceRehydrationCurrentSecretEnv, test.current)
			t.Setenv(evidenceRehydrationPreviousSecretEnv, test.previous)

			_, err := LoadEvidenceRehydrationRuntimeConfigFromEnv()

			require.ErrorIs(t, err, ErrInvalidEvidenceRehydrationRuntimeConfig)
		})
	}
}
