package aiagent

import (
	"encoding/base64"
	"errors"
	"os"
	"strings"
)

const (
	evidenceRehydrationEnabledEnv        = "AI_AGENT_REHYDRATION_ENABLED"
	evidenceRehydrationCurrentSecretEnv  = "AI_AGENT_REHYDRATION_SECRET_CURRENT"
	evidenceRehydrationPreviousSecretEnv = "AI_AGENT_REHYDRATION_SECRET_PREVIOUS"
)

var ErrInvalidEvidenceRehydrationRuntimeConfig = errors.New("invalid evidence rehydration runtime configuration")

// EvidenceRehydrationRuntimeConfig is the disabled-by-default Memos-side
// ownership contract. Secrets are deployment-injected and never persisted.
type EvidenceRehydrationRuntimeConfig struct {
	Enabled        bool
	CurrentSecret  string
	PreviousSecret string
}

func LoadEvidenceRehydrationRuntimeConfigFromEnv() (EvidenceRehydrationRuntimeConfig, error) {
	enabled, err := parseStrictEvidenceRehydrationBool(os.Getenv(evidenceRehydrationEnabledEnv))
	if err != nil || !enabled {
		return EvidenceRehydrationRuntimeConfig{}, err
	}
	if strings.TrimSpace(strings.ToLower(os.Getenv("AI_AGENT_ENABLED"))) != "true" {
		return EvidenceRehydrationRuntimeConfig{}, ErrInvalidEvidenceRehydrationRuntimeConfig
	}
	config := EvidenceRehydrationRuntimeConfig{
		Enabled:        true,
		CurrentSecret:  strings.TrimSpace(os.Getenv(evidenceRehydrationCurrentSecretEnv)),
		PreviousSecret: strings.TrimSpace(os.Getenv(evidenceRehydrationPreviousSecretEnv)),
	}
	delegationSecret := strings.TrimSpace(os.Getenv("AI_AGENT_INTERNAL_SECRET"))
	if err := config.Validate(delegationSecret); err != nil {
		return EvidenceRehydrationRuntimeConfig{}, err
	}
	return config, nil
}

func (config EvidenceRehydrationRuntimeConfig) Validate(delegationSecret string) error {
	if !config.Enabled {
		return nil
	}
	delegationSecret = strings.TrimSpace(delegationSecret)
	if !validEvidenceRehydrationRuntimeSecret(config.CurrentSecret) ||
		(config.PreviousSecret != "" && !validEvidenceRehydrationRuntimeSecret(config.PreviousSecret)) ||
		config.CurrentSecret == config.PreviousSecret ||
		config.CurrentSecret == delegationSecret ||
		(config.PreviousSecret != "" && config.PreviousSecret == delegationSecret) {
		return ErrInvalidEvidenceRehydrationRuntimeConfig
	}
	return nil
}

func parseStrictEvidenceRehydrationBool(value string) (bool, error) {
	switch strings.TrimSpace(strings.ToLower(value)) {
	case "", "false":
		return false, nil
	case "true":
		return true, nil
	default:
		return false, ErrInvalidEvidenceRehydrationRuntimeConfig
	}
}

func validEvidenceRehydrationRuntimeSecret(value string) bool {
	if len(value) != 43 {
		return false
	}
	decoded, err := base64.RawURLEncoding.DecodeString(value)
	return err == nil && len(decoded) == 32 && base64.RawURLEncoding.EncodeToString(decoded) == value
}
