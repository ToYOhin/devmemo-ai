package aiagent

import (
	"os"
	"strings"
)

// LoadConfigFromEnv reads the isolated Agent settings. Disabled is the only default.
func LoadConfigFromEnv() (Config, error) {
	rawEnabled := strings.TrimSpace(strings.ToLower(os.Getenv("AI_AGENT_ENABLED")))
	config := Config{
		InternalURL: strings.TrimSpace(os.Getenv("AI_AGENT_INTERNAL_URL")),
		Secret:      strings.TrimSpace(os.Getenv("AI_AGENT_INTERNAL_SECRET")),
	}
	switch rawEnabled {
	case "", "false":
		return config, nil
	case "true":
		config.Enabled = true
		if err := config.Validate(); err != nil {
			return Config{}, err
		}
		return config, nil
	default:
		return Config{}, ErrInvalidConfig
	}
}
