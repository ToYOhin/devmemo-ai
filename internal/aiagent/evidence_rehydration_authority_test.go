package aiagent

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"testing"

	"github.com/stretchr/testify/require"
)

type fakeEvidenceCurrentAuthorityReader struct {
	snapshot      EvidenceCurrentAuthoritySnapshot
	err           error
	mutateRequest func(*EvidenceRehydrationRequest)
	calls         int
	request       EvidenceRehydrationRequest
	binding       EvidenceAuthorityContextBinding
}

func (f *fakeEvidenceCurrentAuthorityReader) ReadCurrentAuthority(
	request EvidenceRehydrationRequest,
	binding EvidenceAuthorityContextBinding,
) (EvidenceCurrentAuthoritySnapshot, error) {
	f.calls++
	if f.mutateRequest != nil {
		f.mutateRequest(&request)
	}
	f.request = request
	f.binding = binding
	return f.snapshot, f.err
}

func syntheticAuthorityRequestAndSnapshot() (
	EvidenceRehydrationRequest,
	EvidenceAuthorityContextBinding,
	EvidenceCurrentAuthoritySnapshot,
) {
	documents := []string{
		"# Synthetic Memo One\n\nMemos remains the current authority.",
		"# Synthetic Memo Two\n\nOnly current visible content is eligible.",
	}
	hashes := make([]string, len(documents))
	for index, document := range documents {
		digest := sha256.Sum256([]byte(document))
		hashes[index] = fmt.Sprintf("%x", digest)
	}
	request := EvidenceRehydrationRequest{
		Version:           evidenceRehydrationContentVersion,
		SnapshotToken:     "snapshot-synthetic-1",
		MemosAuthorityRef: "authority-ref-synthetic-4",
		Selections: []EvidenceRehydrationSelection{
			{
				SelectionRef:   "rehydration-1",
				MemoUID:        "memo-visible-one",
				SourceSequence: 3,
				DocumentHash:   hashes[0],
				IndexVersion:   "memo-v1",
			},
			{
				SelectionRef:   "rehydration-2",
				MemoUID:        "memo-visible-two",
				SourceSequence: 8,
				DocumentHash:   hashes[1],
				IndexVersion:   "memo-v1",
			},
		},
	}
	binding := EvidenceAuthorityContextBinding{
		MemosAuthorityRef:         request.MemosAuthorityRef,
		AuthenticatedContextToken: "authenticated-context-synthetic-7",
	}
	snapshot := EvidenceCurrentAuthoritySnapshot{
		MemosAuthorityRef:         request.MemosAuthorityRef,
		AuthenticatedContextToken: binding.AuthenticatedContextToken,
		SnapshotRevision:          "current-snapshot-revision-11",
		AuthorityToken:            "authority-synthetic-9",
		Documents: []EvidenceCurrentAuthorityDocument{
			{
				MemoUID:          request.Selections[1].MemoUID,
				Document:         documents[1],
				SourceSequence:   request.Selections[1].SourceSequence,
				DocumentHash:     request.Selections[1].DocumentHash,
				IndexVersion:     "memo-v1",
				Visibility:       EvidenceAuthorityVisibilityCurrent,
				MemoType:         EvidenceAuthorityMemoTypeComplete,
				RowState:         EvidenceAuthorityRowStateNormal,
				LifecycleState:   EvidenceAuthorityLifecycleCurrent,
				SnapshotRevision: "current-snapshot-revision-11",
				AuthorityToken:   "authority-synthetic-9",
			},
			{
				MemoUID:          request.Selections[0].MemoUID,
				Document:         documents[0],
				SourceSequence:   request.Selections[0].SourceSequence,
				DocumentHash:     request.Selections[0].DocumentHash,
				IndexVersion:     "memo-v1",
				Visibility:       EvidenceAuthorityVisibilityCurrent,
				MemoType:         EvidenceAuthorityMemoTypeComplete,
				RowState:         EvidenceAuthorityRowStateNormal,
				LifecycleState:   EvidenceAuthorityLifecycleCurrent,
				SnapshotRevision: "current-snapshot-revision-11",
				AuthorityToken:   "authority-synthetic-9",
			},
		},
	}
	return request, binding, snapshot
}

func TestEvidenceAuthorityBuildsExactAllOrNothingResponse(t *testing.T) {
	request, binding, snapshot := syntheticAuthorityRequestAndSnapshot()
	reader := &fakeEvidenceCurrentAuthorityReader{snapshot: snapshot}

	response, err := BuildEvidenceRehydrationResponse(request, binding, reader)
	require.NoError(t, err)
	require.Equal(t, 1, reader.calls)
	require.Equal(t, request, reader.request)
	require.Equal(t, binding, reader.binding)
	require.Equal(t, request.SnapshotToken, response.SnapshotToken)
	require.Equal(t, snapshot.AuthorityToken, response.AuthorityToken)
	require.Len(t, response.Documents, 2)
	require.Equal(t, request.Selections[0].SelectionRef, response.Documents[0].SelectionRef)
	require.Equal(t, snapshot.Documents[1].Document, response.Documents[0].Document)
	require.Equal(t, request.Selections[1].SelectionRef, response.Documents[1].SelectionRef)
	require.Equal(t, snapshot.Documents[0].Document, response.Documents[1].Document)

	body, err := json.Marshal(response)
	require.NoError(t, err)
	parsed, err := ParseEvidenceRehydrationResponse(body, 200, request)
	require.NoError(t, err)
	require.Equal(t, response, *parsed.Response)
	var fields map[string]json.RawMessage
	require.NoError(t, json.Unmarshal(body, &fields))
	require.ElementsMatch(t, []string{"version", "snapshot_token", "authority_token", "documents"}, mapKeysToStrings(fields))
	for _, forbidden := range []string{
		"memo_uid", "memos_authority_ref", "authenticated_context", "visibility",
		"owner", "caller", "citation", "store", "payload",
	} {
		require.NotContains(t, string(body), forbidden)
	}
}

func TestEvidenceAuthorityBindingHasNoCallerControlledIdentityOrVisibility(t *testing.T) {
	typeOfBinding := reflect.TypeOf(EvidenceAuthorityContextBinding{})
	require.Equal(t, 2, typeOfBinding.NumField())
	require.Equal(t, "MemosAuthorityRef", typeOfBinding.Field(0).Name)
	require.Equal(t, "AuthenticatedContextToken", typeOfBinding.Field(1).Name)
}

func TestEvidenceAuthorityReaderCannotRewriteVerifiedSelectionIdentity(t *testing.T) {
	request, binding, snapshot := syntheticAuthorityRequestAndSnapshot()
	originalRequest := cloneEvidenceRehydrationRequest(request)
	reader := &fakeEvidenceCurrentAuthorityReader{
		snapshot: snapshot,
		mutateRequest: func(value *EvidenceRehydrationRequest) {
			value.Selections[0].SelectionRef = "rehydration-99"
			value.Selections[0].MemoUID = "memo-attacker"
		},
	}

	response, err := BuildEvidenceRehydrationResponse(request, binding, reader)
	require.NoError(t, err)
	require.Equal(t, originalRequest, request)
	require.Equal(t, originalRequest.Selections[0].SelectionRef, response.Documents[0].SelectionRef)
	require.NotEqual(t, reader.request.Selections[0].SelectionRef, response.Documents[0].SelectionRef)
}

func TestEvidenceAuthorityRejectsIneligibleCurrentMemoState(t *testing.T) {
	request, binding, snapshot := syntheticAuthorityRequestAndSnapshot()
	tests := []struct {
		name   string
		mutate func(*EvidenceCurrentAuthorityDocument)
	}{
		{name: "visibility lost", mutate: func(document *EvidenceCurrentAuthorityDocument) {
			document.Visibility = EvidenceAuthorityVisibility("not-visible")
		}},
		{name: "comment", mutate: func(document *EvidenceCurrentAuthorityDocument) {
			document.MemoType = EvidenceAuthorityMemoType("comment")
		}},
		{name: "blank type", mutate: func(document *EvidenceCurrentAuthorityDocument) {
			document.MemoType = EvidenceAuthorityMemoType("blank")
		}},
		{name: "archive", mutate: func(document *EvidenceCurrentAuthorityDocument) {
			document.RowState = EvidenceAuthorityRowState("archived")
		}},
		{name: "delete", mutate: func(document *EvidenceCurrentAuthorityDocument) {
			document.RowState = EvidenceAuthorityRowState("deleted")
		}},
		{name: "tombstone", mutate: func(document *EvidenceCurrentAuthorityDocument) {
			document.LifecycleState = EvidenceAuthorityLifecycleState("tombstone")
		}},
		{name: "blank content", mutate: func(document *EvidenceCurrentAuthorityDocument) { document.Document = "  " }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			changed := snapshot
			changed.Documents = append([]EvidenceCurrentAuthorityDocument(nil), snapshot.Documents...)
			test.mutate(&changed.Documents[0])
			response, err := BuildEvidenceRehydrationResponse(request, binding, &fakeEvidenceCurrentAuthorityReader{snapshot: changed})
			require.Equal(t, EvidenceRehydrationResponse{}, response)
			require.EqualError(t, err, "authorized retrieval unavailable")
		})
	}
}

func TestEvidenceAuthorityRejectsReaderFailureWithoutDetail(t *testing.T) {
	request, binding, snapshot := syntheticAuthorityRequestAndSnapshot()
	reader := &fakeEvidenceCurrentAuthorityReader{
		snapshot: snapshot,
		err:      errors.New("raw memo private query identity visibility secret"),
	}

	response, err := BuildEvidenceRehydrationResponse(request, binding, reader)
	require.Equal(t, EvidenceRehydrationResponse{}, response)
	require.EqualError(t, err, "authorized retrieval unavailable")
	for _, forbidden := range []string{"raw memo", "query", "identity", "visibility", "secret", "authority-ref"} {
		require.NotContains(t, err.Error(), forbidden)
	}
}

func TestEvidenceAuthorityRejectsInvalidRequestOrBindingBeforeReading(t *testing.T) {
	request, binding, snapshot := syntheticAuthorityRequestAndSnapshot()
	tests := []struct {
		name    string
		request EvidenceRehydrationRequest
		binding EvidenceAuthorityContextBinding
	}{
		{
			name: "unverified request value",
			request: func() EvidenceRehydrationRequest {
				changed := request
				changed.Version = "unknown"
				return changed
			}(),
			binding: binding,
		},
		{
			name:    "authority ref mismatch",
			request: request,
			binding: EvidenceAuthorityContextBinding{
				MemosAuthorityRef:         "authority-ref-other",
				AuthenticatedContextToken: binding.AuthenticatedContextToken,
			},
		},
		{
			name:    "missing authenticated context",
			request: request,
			binding: EvidenceAuthorityContextBinding{MemosAuthorityRef: request.MemosAuthorityRef},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			reader := &fakeEvidenceCurrentAuthorityReader{snapshot: snapshot}
			response, err := BuildEvidenceRehydrationResponse(test.request, test.binding, reader)
			require.Equal(t, EvidenceRehydrationResponse{}, response)
			require.EqualError(t, err, "authorized retrieval unavailable")
			require.Zero(t, reader.calls)
		})
	}

	response, err := BuildEvidenceRehydrationResponse(request, binding, nil)
	require.Equal(t, EvidenceRehydrationResponse{}, response)
	require.EqualError(t, err, "authorized retrieval unavailable")
}

func TestEvidenceAuthorityRejectsAtomicSnapshotBindingMismatch(t *testing.T) {
	request, binding, snapshot := syntheticAuthorityRequestAndSnapshot()
	tests := []struct {
		name   string
		mutate func(*EvidenceCurrentAuthoritySnapshot)
	}{
		{name: "authority ref", mutate: func(value *EvidenceCurrentAuthoritySnapshot) { value.MemosAuthorityRef = "authority-ref-other" }},
		{name: "authenticated context", mutate: func(value *EvidenceCurrentAuthoritySnapshot) {
			value.AuthenticatedContextToken = "authenticated-context-other"
		}},
		{name: "missing revision", mutate: func(value *EvidenceCurrentAuthoritySnapshot) { value.SnapshotRevision = "" }},
		{name: "malformed revision", mutate: func(value *EvidenceCurrentAuthoritySnapshot) { value.SnapshotRevision = "revision with spaces" }},
		{name: "missing authority token", mutate: func(value *EvidenceCurrentAuthoritySnapshot) { value.AuthorityToken = "" }},
		{name: "malformed authority token", mutate: func(value *EvidenceCurrentAuthoritySnapshot) { value.AuthorityToken = "authority/token" }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			changed := snapshot
			test.mutate(&changed)
			reader := &fakeEvidenceCurrentAuthorityReader{snapshot: changed}
			response, err := BuildEvidenceRehydrationResponse(request, binding, reader)
			require.Equal(t, EvidenceRehydrationResponse{}, response)
			require.EqualError(t, err, "authorized retrieval unavailable")
			require.Equal(t, 1, reader.calls)
		})
	}
}

func TestEvidenceAuthorityRequiresOneCurrentDocumentPerRequestedUID(t *testing.T) {
	request, binding, snapshot := syntheticAuthorityRequestAndSnapshot()
	tests := []struct {
		name   string
		mutate func(*EvidenceCurrentAuthoritySnapshot)
	}{
		{name: "missing", mutate: func(value *EvidenceCurrentAuthoritySnapshot) { value.Documents = value.Documents[:1] }},
		{name: "extra", mutate: func(value *EvidenceCurrentAuthoritySnapshot) {
			value.Documents = append(value.Documents, value.Documents[0])
		}},
		{name: "duplicate uid", mutate: func(value *EvidenceCurrentAuthoritySnapshot) { value.Documents[1].MemoUID = value.Documents[0].MemoUID }},
		{name: "unknown uid", mutate: func(value *EvidenceCurrentAuthoritySnapshot) { value.Documents[1].MemoUID = "memo-unknown" }},
		{name: "malformed uid", mutate: func(value *EvidenceCurrentAuthoritySnapshot) { value.Documents[1].MemoUID = "memo_unknown" }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			changed := snapshot
			changed.Documents = append([]EvidenceCurrentAuthorityDocument(nil), snapshot.Documents...)
			test.mutate(&changed)
			response, err := BuildEvidenceRehydrationResponse(request, binding, &fakeEvidenceCurrentAuthorityReader{snapshot: changed})
			require.Equal(t, EvidenceRehydrationResponse{}, response)
			require.EqualError(t, err, "authorized retrieval unavailable")
		})
	}
}

func TestEvidenceAuthorityRejectsUpdateDeleteAndMixedSnapshotRows(t *testing.T) {
	request, binding, snapshot := syntheticAuthorityRequestAndSnapshot()
	tests := []struct {
		name   string
		mutate func(*EvidenceCurrentAuthorityDocument)
	}{
		{name: "concurrent sequence update", mutate: func(document *EvidenceCurrentAuthorityDocument) { document.SourceSequence++ }},
		{name: "concurrent hash update", mutate: func(document *EvidenceCurrentAuthorityDocument) { document.DocumentHash = fmt.Sprintf("%064d", 0) }},
		{name: "index version", mutate: func(document *EvidenceCurrentAuthorityDocument) { document.IndexVersion = "memo-chunk-v1" }},
		{name: "document hash mismatch", mutate: func(document *EvidenceCurrentAuthorityDocument) { document.Document += " changed" }},
		{name: "mixed snapshot revision", mutate: func(document *EvidenceCurrentAuthorityDocument) {
			document.SnapshotRevision = "current-snapshot-revision-12"
		}},
		{name: "mixed authority token", mutate: func(document *EvidenceCurrentAuthorityDocument) { document.AuthorityToken = "authority-synthetic-10" }},
		{name: "invalid utf8", mutate: func(document *EvidenceCurrentAuthorityDocument) { document.Document = string([]byte{0xff}) }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			changed := snapshot
			changed.Documents = append([]EvidenceCurrentAuthorityDocument(nil), snapshot.Documents...)
			test.mutate(&changed.Documents[0])
			response, err := BuildEvidenceRehydrationResponse(request, binding, &fakeEvidenceCurrentAuthorityReader{snapshot: changed})
			require.Equal(t, EvidenceRehydrationResponse{}, response)
			require.EqualError(t, err, "authorized retrieval unavailable")
			require.Empty(t, response.Documents)
		})
	}
}

func TestEvidenceAuthorityRejectsSelectionMismatchWithoutPartialResponse(t *testing.T) {
	request, binding, snapshot := syntheticAuthorityRequestAndSnapshot()
	changedRequest := request
	changedRequest.Selections = append([]EvidenceRehydrationSelection(nil), request.Selections...)
	changedRequest.Selections[1].DocumentHash = fmt.Sprintf("%064d", 1)

	response, err := BuildEvidenceRehydrationResponse(
		changedRequest,
		binding,
		&fakeEvidenceCurrentAuthorityReader{snapshot: snapshot},
	)
	require.Equal(t, EvidenceRehydrationResponse{}, response)
	require.Empty(t, response.Documents)
	require.EqualError(t, err, "authorized retrieval unavailable")
}

func mapKeysToStrings(value map[string]json.RawMessage) []string {
	keys := reflect.ValueOf(value).MapKeys()
	result := make([]string, 0, len(keys))
	for _, key := range keys {
		result = append(result, key.String())
	}
	return result
}
