package aiagent

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"
)

var ErrLifecycleHTTP = errors.New("memo lifecycle transport unavailable")

type LifecycleEventRequest struct {
	EventID        string  `json:"event_id"`
	EventType      string  `json:"event_type"`
	MemoUID        string  `json:"memo_uid"`
	SourceSequence int64   `json:"source_sequence"`
	IndexVersion   string  `json:"index_version"`
	Operation      string  `json:"operation"`
	Reason         string  `json:"reason"`
	OccurredAt     string  `json:"occurred_at"`
	Document       *string `json:"document,omitempty"`
	DocumentHash   *string `json:"document_hash,omitempty"`
}

type LifecycleHTTPClient struct {
	config LifecycleRuntimeConfig
	doer   httpDoer
	now    func() time.Time
	nonce  func() (string, error)
}

func NewLifecycleHTTPClient(config LifecycleRuntimeConfig) (*LifecycleHTTPClient, error) {
	if !config.Enabled || !validLifecycleRuntimeShape(config) {
		return nil, ErrInvalidLifecycleRuntimeConfig
	}
	client := &http.Client{
		Timeout: 5 * time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	return &LifecycleHTTPClient{
		config: config,
		doer:   client,
		now:    time.Now,
		nonce:  newLifecycleNonce,
	}, nil
}

func (client *LifecycleHTTPClient) Deliver(
	ctx context.Context, event LifecycleEventRequest,
) (LifecycleAcknowledgement, error) {
	body, err := json.Marshal(event)
	if err != nil {
		return LifecycleAcknowledgement{}, ErrLifecycleHTTP
	}
	nonce, err := client.nonce()
	if err != nil {
		return LifecycleAcknowledgement{}, ErrLifecycleHTTP
	}
	headers, err := SignLifecycleRequest(body, client.now(), nonce, client.config.Secret)
	if err != nil {
		return LifecycleAcknowledgement{}, ErrLifecycleHTTP
	}
	response, err := client.post(ctx, InternalLifecyclePath, body, headers)
	if err != nil {
		return LifecycleAcknowledgement{}, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK || response.Header.Get("Content-Type") != "application/json" {
		return LifecycleAcknowledgement{}, ErrLifecycleHTTP
	}
	responseBody, err := readBoundedLifecycleBody(response.Body, maxLifecycleAckBytes)
	if err != nil {
		return LifecycleAcknowledgement{}, ErrLifecycleHTTP
	}
	acknowledgement, err := ParseLifecycleAcknowledgement(responseBody)
	if err != nil || acknowledgement.EventID != event.EventID ||
		acknowledgement.MemoUID != event.MemoUID ||
		acknowledgement.SourceSequence != event.SourceSequence ||
		acknowledgement.IndexVersion != event.IndexVersion ||
		acknowledgement.Operation != event.Operation {
		return LifecycleAcknowledgement{}, ErrLifecycleHTTP
	}
	return acknowledgement, nil
}

func (client *LifecycleHTTPClient) Activate(
	ctx context.Context, activation LifecycleActivationRequest,
) error {
	body, err := json.Marshal(activation)
	if err != nil {
		return ErrLifecycleHTTP
	}
	nonce, err := client.nonce()
	if err != nil {
		return ErrLifecycleHTTP
	}
	headers, err := SignLifecycleActivationRequest(
		body, client.now(), nonce, client.config.Secret,
	)
	if err != nil {
		return ErrLifecycleHTTP
	}
	response, err := client.post(ctx, InternalLifecycleActivationPath, body, headers)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	responseBody, err := readBoundedLifecycleBody(response.Body, 1)
	if err != nil || response.StatusCode != http.StatusNoContent || len(responseBody) != 0 {
		return ErrLifecycleHTTP
	}
	return nil
}

func (client *LifecycleHTTPClient) post(
	ctx context.Context,
	path string,
	body []byte,
	headers LifecycleSignedHeaders,
) (*http.Response, error) {
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		strings.TrimRight(client.config.InternalURL, "/")+path,
		bytes.NewReader(body),
	)
	if err != nil {
		return nil, ErrLifecycleHTTP
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(LifecycleSignatureHeader, headers.Signature)
	request.Header.Set(LifecycleTimestampHeader, headers.Timestamp)
	request.Header.Set(LifecycleNonceHeader, headers.Nonce)
	response, err := client.doer.Do(request)
	if err != nil {
		return nil, ErrLifecycleHTTP
	}
	return response, nil
}

func readBoundedLifecycleBody(reader io.Reader, limit int64) ([]byte, error) {
	body, err := io.ReadAll(io.LimitReader(reader, limit+1))
	if err != nil || int64(len(body)) > limit {
		return nil, ErrLifecycleHTTP
	}
	return body, nil
}

func newLifecycleNonce() (string, error) {
	buffer := make([]byte, 18)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buffer), nil
}
