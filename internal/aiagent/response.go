package aiagent

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"strings"
)

const agentVersion = "evidence-answer-agent-v1"

// AnswerResponse is the only AI result shape the Memos BFF may return to a browser.
type AnswerResponse struct {
	Answer         string     `json:"answer"`
	Citations      []Citation `json:"citations"`
	Provider       string     `json:"provider"`
	RetrievedCount int        `json:"retrieved_count"`
	AgentVersion   string     `json:"agent_version"`
	Trace          Trace      `json:"trace"`
}

type Citation struct {
	MemoID      string   `json:"memo_id"`
	EmbeddingID string   `json:"embedding_id"`
	Score       float64  `json:"score"`
	Title       string   `json:"title"`
	Summary     string   `json:"summary"`
	SourceRefs  []string `json:"source_refs"`
	Metadata    Metadata `json:"metadata"`
}

type Metadata struct {
	MemoType     string   `json:"memo_type"`
	Tags         []string `json:"tags"`
	IndexVersion string   `json:"index_version"`
}

type Trace struct {
	TerminalState string `json:"terminal_state"`
	Steps         []Step `json:"steps"`
}

type Step struct {
	Index       int    `json:"index"`
	Kind        string `json:"kind"`
	Name        string `json:"name"`
	Status      string `json:"status"`
	ResultCount *int   `json:"result_count,omitempty"`
}

func decodeAnswerResponse(body []byte, visibleMemoUIDs []string) (AnswerResponse, error) {
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	var response AnswerResponse
	if err := decoder.Decode(&response); err != nil {
		return AnswerResponse{}, err
	}
	if err := requireJSONEOF(decoder); err != nil {
		return AnswerResponse{}, err
	}
	if err := response.Validate(visibleMemoUIDs); err != nil {
		return AnswerResponse{}, err
	}
	return response, nil
}

func requireJSONEOF(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return errors.New("unexpected response data")
	}
	return nil
}

// Validate verifies that no untrusted AI response can extend the browser contract.
func (r AnswerResponse) Validate(visibleMemoUIDs []string) error {
	if strings.TrimSpace(r.Answer) == "" || strings.TrimSpace(r.Provider) == "" || r.AgentVersion != agentVersion {
		return errors.New("invalid answer response")
	}
	if r.RetrievedCount != len(r.Citations) {
		return errors.New("invalid citation count")
	}
	visible := make(map[string]struct{}, len(visibleMemoUIDs))
	for _, uid := range visibleMemoUIDs {
		visible[uid] = struct{}{}
	}
	for _, citation := range r.Citations {
		if err := citation.validate(visible); err != nil {
			return err
		}
	}
	return r.Trace.validate(len(r.Citations))
}

func (c Citation) validate(visible map[string]struct{}) error {
	if _, ok := visible[c.MemoID]; !ok || strings.TrimSpace(c.EmbeddingID) == "" || len(c.Title) > 240 || len(c.Summary) > 1000 || len(c.SourceRefs) > 20 {
		return errors.New("invalid citation")
	}
	for _, sourceRef := range c.SourceRefs {
		if strings.TrimSpace(sourceRef) == "" {
			return errors.New("invalid citation source")
		}
	}
	if strings.TrimSpace(c.Metadata.MemoType) == "" || c.Metadata.IndexVersion != "memo-v1" || len(c.Metadata.Tags) > 20 {
		return errors.New("invalid citation metadata")
	}
	for _, tag := range c.Metadata.Tags {
		if strings.TrimSpace(tag) == "" {
			return errors.New("invalid citation metadata")
		}
	}
	return nil
}

func (t Trace) validate(citationCount int) error {
	if t.TerminalState != "answered" && t.TerminalState != "no_context" {
		return errors.New("invalid trace")
	}
	if len(t.Steps) < 1 || len(t.Steps) > 2 {
		return errors.New("invalid trace")
	}
	tool := t.Steps[0]
	if tool.Index != 1 || tool.Kind != "tool" || tool.Name != "search_memos" || tool.Status != "completed" || tool.ResultCount == nil || *tool.ResultCount != citationCount {
		return errors.New("invalid trace")
	}
	if t.TerminalState == "no_context" {
		if citationCount != 0 || len(t.Steps) != 1 {
			return errors.New("invalid trace")
		}
		return nil
	}
	if len(t.Steps) != 2 {
		return errors.New("invalid trace")
	}
	final := t.Steps[1]
	if final.Index != 2 || final.Kind != "final" || final.Name != "answer_from_evidence" || final.Status != "completed" || final.ResultCount != nil {
		return errors.New("invalid trace")
	}
	return nil
}
