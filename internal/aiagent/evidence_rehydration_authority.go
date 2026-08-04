package aiagent

import (
	"crypto/sha256"
	"fmt"
	"strings"
	"unicode/utf8"
)

// EvidenceAuthorityVisibility is a Memos-owned current visibility assertion.
type EvidenceAuthorityVisibility string

// EvidenceAuthorityMemoType is a Memos-owned complete-Memo assertion.
type EvidenceAuthorityMemoType string

// EvidenceAuthorityRowState is a Memos-owned current row-state assertion.
type EvidenceAuthorityRowState string

// EvidenceAuthorityLifecycleState is a Memos-owned source lifecycle assertion.
type EvidenceAuthorityLifecycleState string

const (
	EvidenceAuthorityVisibilityCurrent EvidenceAuthorityVisibility     = "current-visible"
	EvidenceAuthorityMemoTypeComplete  EvidenceAuthorityMemoType       = "complete"
	EvidenceAuthorityRowStateNormal    EvidenceAuthorityRowState       = "normal"
	EvidenceAuthorityLifecycleCurrent  EvidenceAuthorityLifecycleState = "current"
)

// EvidenceAuthorityContextBinding is an opaque Memos-internal binding to an
// already authenticated caller. It deliberately has no identity or visibility
// fields that a browser or AI caller could populate.
type EvidenceAuthorityContextBinding struct {
	MemosAuthorityRef         string
	AuthenticatedContextToken string
}

// EvidenceCurrentAuthorityDocument is one entry from the same atomic Memos
// current-authority snapshot. Its state assertions are owned by Memos; request
// fields and derived stores cannot manufacture eligibility.
type EvidenceCurrentAuthorityDocument struct {
	MemoUID          string
	Document         string
	SourceSequence   int64
	DocumentHash     string
	IndexVersion     string
	Visibility       EvidenceAuthorityVisibility
	MemoType         EvidenceAuthorityMemoType
	RowState         EvidenceAuthorityRowState
	LifecycleState   EvidenceAuthorityLifecycleState
	SnapshotRevision string
	AuthorityToken   string
}

// EvidenceCurrentAuthoritySnapshot is an all-or-nothing current Memos read.
// The authority reference and authenticated-context token remain request-local
// and are never projected into the response.
type EvidenceCurrentAuthoritySnapshot struct {
	MemosAuthorityRef         string
	AuthenticatedContextToken string
	SnapshotRevision          string
	AuthorityToken            string
	Documents                 []EvidenceCurrentAuthorityDocument
}

// EvidenceCurrentAuthorityReader is the smallest future single-host handler
// boundary. Implementations must obtain the returned value in one atomic read.
// R5-I6 supplies no store, repository, route, transport, or runtime adapter.
type EvidenceCurrentAuthorityReader interface {
	ReadCurrentAuthority(
		request EvidenceRehydrationRequest,
		binding EvidenceAuthorityContextBinding,
	) (EvidenceCurrentAuthoritySnapshot, error)
}

// BuildEvidenceRehydrationResponse re-confirms current Memos authority after
// R5-I5 has verified and exactly parsed the transport request. Every failure is
// projected to the same content-free error and no partial document is returned.
func BuildEvidenceRehydrationResponse(
	request EvidenceRehydrationRequest,
	binding EvidenceAuthorityContextBinding,
	reader EvidenceCurrentAuthorityReader,
) (EvidenceRehydrationResponse, error) {
	if !validEvidenceRehydrationRequestValue(request) ||
		!validEvidenceAuthorityBinding(request, binding) || reader == nil {
		return EvidenceRehydrationResponse{}, evidenceRehydrationUnavailable()
	}
	verifiedRequest := cloneEvidenceRehydrationRequest(request)

	snapshot, err := reader.ReadCurrentAuthority(cloneEvidenceRehydrationRequest(verifiedRequest), binding)
	if err != nil || !validEvidenceAuthoritySnapshotBinding(verifiedRequest, binding, snapshot) {
		return EvidenceRehydrationResponse{}, evidenceRehydrationUnavailable()
	}

	byUID := make(map[string]EvidenceCurrentAuthorityDocument, len(snapshot.Documents))
	for _, document := range snapshot.Documents {
		if !validEvidenceCurrentAuthorityDocument(document, snapshot) {
			return EvidenceRehydrationResponse{}, evidenceRehydrationUnavailable()
		}
		if _, duplicate := byUID[document.MemoUID]; duplicate {
			return EvidenceRehydrationResponse{}, evidenceRehydrationUnavailable()
		}
		byUID[document.MemoUID] = document
	}
	if len(byUID) != len(verifiedRequest.Selections) {
		return EvidenceRehydrationResponse{}, evidenceRehydrationUnavailable()
	}

	response := EvidenceRehydrationResponse{
		Version:        evidenceRehydrationContentVersion,
		SnapshotToken:  verifiedRequest.SnapshotToken,
		AuthorityToken: snapshot.AuthorityToken,
		Documents:      make([]EvidenceRehydrationDocument, 0, len(verifiedRequest.Selections)),
	}
	for _, selection := range verifiedRequest.Selections {
		document, ok := byUID[selection.MemoUID]
		if !ok || document.SourceSequence != selection.SourceSequence ||
			document.DocumentHash != selection.DocumentHash ||
			document.IndexVersion != selection.IndexVersion {
			return EvidenceRehydrationResponse{}, evidenceRehydrationUnavailable()
		}
		response.Documents = append(response.Documents, EvidenceRehydrationDocument{
			SelectionRef:   selection.SelectionRef,
			Document:       document.Document,
			SourceSequence: document.SourceSequence,
			DocumentHash:   document.DocumentHash,
			IndexVersion:   document.IndexVersion,
		})
	}
	if !responseMatchesEvidenceRehydrationRequest(response, verifiedRequest) {
		return EvidenceRehydrationResponse{}, evidenceRehydrationUnavailable()
	}
	return response, nil
}

func cloneEvidenceRehydrationRequest(request EvidenceRehydrationRequest) EvidenceRehydrationRequest {
	cloned := request
	cloned.Selections = append([]EvidenceRehydrationSelection(nil), request.Selections...)
	return cloned
}

func validEvidenceAuthorityBinding(
	request EvidenceRehydrationRequest,
	binding EvidenceAuthorityContextBinding,
) bool {
	return evidenceRehydrationOpaqueIDPattern.MatchString(binding.MemosAuthorityRef) &&
		evidenceRehydrationOpaqueIDPattern.MatchString(binding.AuthenticatedContextToken) &&
		binding.MemosAuthorityRef == request.MemosAuthorityRef
}

func validEvidenceAuthoritySnapshotBinding(
	request EvidenceRehydrationRequest,
	binding EvidenceAuthorityContextBinding,
	snapshot EvidenceCurrentAuthoritySnapshot,
) bool {
	return snapshot.MemosAuthorityRef == binding.MemosAuthorityRef &&
		binding.MemosAuthorityRef == request.MemosAuthorityRef &&
		snapshot.AuthenticatedContextToken == binding.AuthenticatedContextToken &&
		evidenceRehydrationOpaqueIDPattern.MatchString(snapshot.SnapshotRevision) &&
		evidenceRehydrationOpaqueIDPattern.MatchString(snapshot.AuthorityToken) &&
		len(snapshot.Documents) == len(request.Selections)
}

func validEvidenceCurrentAuthorityDocument(
	document EvidenceCurrentAuthorityDocument,
	snapshot EvidenceCurrentAuthoritySnapshot,
) bool {
	if !evidenceRehydrationMemoUIDPattern.MatchString(document.MemoUID) ||
		strings.TrimSpace(document.Document) == "" || !utf8.ValidString(document.Document) ||
		utf8.RuneCountInString(document.Document) > maxEvidenceRehydrationDocumentChars ||
		document.SourceSequence < 1 ||
		!evidenceRehydrationHashPattern.MatchString(document.DocumentHash) ||
		document.IndexVersion != "memo-v1" ||
		document.Visibility != EvidenceAuthorityVisibilityCurrent ||
		document.MemoType != EvidenceAuthorityMemoTypeComplete ||
		document.RowState != EvidenceAuthorityRowStateNormal ||
		document.LifecycleState != EvidenceAuthorityLifecycleCurrent ||
		document.SnapshotRevision != snapshot.SnapshotRevision ||
		document.AuthorityToken != snapshot.AuthorityToken {
		return false
	}
	digest := sha256.Sum256([]byte(document.Document))
	return document.DocumentHash == fmt.Sprintf("%x", digest)
}
