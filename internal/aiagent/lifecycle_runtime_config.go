package aiagent

import (
	"errors"
	"net/url"
	"os"
	"regexp"
	"strings"
)

const (
	lifecycleRuntimeEnabledEnv    = "AI_AGENT_LIFECYCLE_ENABLED"
	lifecycleRuntimeSecretEnv     = "AI_AGENT_LIFECYCLE_SECRET"
	lifecycleRuntimeGenerationEnv = "AI_AGENT_LIFECYCLE_GENERATION"
)

var ErrInvalidLifecycleRuntimeConfig = errors.New("invalid lifecycle runtime configuration")
var lifecycleGenerationPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`)

type LifecycleRuntimeConfig struct {
	Enabled     bool
	InternalURL string
	Secret      string
	Generation  string
}

func LoadLifecycleRuntimeConfigFromEnv() (LifecycleRuntimeConfig, error) {
	enabled, err := parseStrictLifecycleBool(os.Getenv(lifecycleRuntimeEnabledEnv))
	if err != nil || !enabled {
		return LifecycleRuntimeConfig{}, err
	}
	rehydration, err := LoadEvidenceRehydrationRuntimeConfigFromEnv()
	if err != nil || !rehydration.Enabled {
		return LifecycleRuntimeConfig{}, ErrInvalidLifecycleRuntimeConfig
	}
	config := LifecycleRuntimeConfig{
		Enabled:     true,
		InternalURL: strings.TrimSpace(os.Getenv("AI_AGENT_INTERNAL_URL")),
		Secret:      strings.TrimSpace(os.Getenv(lifecycleRuntimeSecretEnv)),
		Generation:  strings.TrimSpace(os.Getenv(lifecycleRuntimeGenerationEnv)),
	}
	if err := config.Validate(
		strings.TrimSpace(os.Getenv("AI_AGENT_INTERNAL_SECRET")), rehydration,
	); err != nil {
		return LifecycleRuntimeConfig{}, err
	}
	return config, nil
}

func (config LifecycleRuntimeConfig) Validate(
	delegationSecret string,
	rehydration EvidenceRehydrationRuntimeConfig,
) error {
	if !config.Enabled {
		return nil
	}
	parsed, err := url.Parse(strings.TrimSpace(config.InternalURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		(parsed.Path != "" && parsed.Path != "/") || parsed.RawQuery != "" || parsed.Fragment != "" ||
		!validEvidenceRehydrationRuntimeSecret(config.Secret) ||
		!lifecycleGenerationPattern.MatchString(config.Generation) ||
		!rehydration.Enabled || config.Secret == strings.TrimSpace(delegationSecret) ||
		config.Secret == rehydration.CurrentSecret || config.Secret == rehydration.PreviousSecret {
		return ErrInvalidLifecycleRuntimeConfig
	}
	return nil
}

func parseStrictLifecycleBool(value string) (bool, error) {
	switch strings.TrimSpace(strings.ToLower(value)) {
	case "", "false":
		return false, nil
	case "true":
		return true, nil
	default:
		return false, ErrInvalidLifecycleRuntimeConfig
	}
}
