package fileserver

import (
	"bytes"
	"context"
	"encoding/binary"
	"fmt"
	"image"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"testing/iotest"

	"github.com/labstack/echo/v5"
	"github.com/stretchr/testify/require"

	apiv1 "github.com/usememos/memos/proto/gen/api/v1"
	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/store"
)

func TestGenerateThumbnailTIFFSafety(t *testing.T) {
	for _, test := range []struct {
		name    string
		content []byte
		wantErr string
	}{
		{"valid palette", thumbnailPalettedTIFF(1, 1, 1), ""},
		{"invalid palette", thumbnailPalettedTIFF(2, 1, 1), "invalid color index"},
		// RowsPerStrip is 1 with only one strip supplied. Without a preflight guard,
		// the decoder safely rejects the header before allocation; never decode a huge raster in this test.
		{"oversized dimensions", thumbnailPalettedTIFF(1, 100_000, 100_000), "image dimensions exceed maximum of 50000000 pixels"},
	} {
		t.Run(test.name, func(t *testing.T) {
			fs := &FileServerService{}
			outputPath := filepath.Join(t.TempDir(), "thumbnail.jpg")
			attachment := &store.Attachment{Blob: test.content, Type: "image/png"}

			thumbnail, err := fs.generateThumbnail(context.Background(), attachment, outputPath)
			if test.wantErr != "" {
				require.ErrorContains(t, err, test.wantErr)
				require.Nil(t, thumbnail)
				require.NoFileExists(t, outputPath)
				return
			}
			require.NoError(t, err)
			require.FileExists(t, outputPath)
			config, format, err := image.DecodeConfig(bytes.NewReader(thumbnail))
			require.NoError(t, err)
			require.Equal(t, "jpeg", format)
			require.Equal(t, 1, config.Width)
			require.Equal(t, 1, config.Height)
		})
	}
}

func TestDecodeThumbnailImageReplaysNonSeekableHeader(t *testing.T) {
	content := thumbnailPalettedTIFF(1, 1, 1)
	img, err := decodeThumbnailImage(iotest.OneByteReader(bytes.NewReader(content)))
	require.NoError(t, err)
	require.Equal(t, image.Rect(0, 0, 1, 1), img.Bounds())
}

func TestDecodeThumbnailImageBoundsHeaderProbe(t *testing.T) {
	// Point the TIFF directory beyond the probe budget. This fixture is just over
	// 1 MiB of zeroes, with no image buffer or decompression workload.
	content := make([]byte, thumbnailMetadataProbeSize+16)
	copy(content, []byte{'I', 'I', 42, 0})
	binary.LittleEndian.PutUint32(content[4:8], uint32(thumbnailMetadataProbeSize+8))
	reader := &thumbnailCountingReader{Reader: bytes.NewReader(content)}
	img, err := decodeThumbnailImage(reader)
	require.ErrorContains(t, err, "inspect image dimensions within header budget")
	require.Nil(t, img)
	require.Equal(t, thumbnailMetadataProbeSize, reader.bytesRead)
}

type thumbnailCountingReader struct {
	io.Reader
	bytesRead int
}

func (r *thumbnailCountingReader) Read(p []byte) (int, error) {
	n, err := r.Reader.Read(p)
	r.bytesRead += n
	return n, err
}

func TestServeAttachmentFile_ThumbnailSafetyAndFallback(t *testing.T) {
	for _, test := range []struct {
		name          string
		mimeType      string
		content       []byte
		wantThumbnail bool
	}{
		{"normal PNG", "image/png", testPNGWithChunk(t, "tEXt", []byte("synthetic")), true},
		{"valid TIFF labeled PNG", "image/png", thumbnailPalettedTIFF(1, 1, 1), true},
		{"invalid TIFF", "image/tiff", thumbnailPalettedTIFF(2, 1, 1), false},
		{"invalid TIFF labeled PNG", "image/png", thumbnailPalettedTIFF(2, 1, 1), false},
		{"invalid TIFF labeled JPEG", "image/jpeg", thumbnailPalettedTIFF(2, 1, 1), false},
		{"oversized TIFF labeled PNG", "image/png", thumbnailPalettedTIFF(1, 100_000, 100_000), false},
	} {
		t.Run(test.name, func(t *testing.T) {
			ctx := context.Background()
			svc, fs, _, cleanup := newShareAttachmentTestServices(ctx, t)
			defer cleanup()
			creator, err := svc.Store.CreateUser(ctx, &store.User{
				Username: "thumbnail-safety-owner",
				Role:     store.RoleUser,
				Email:    "thumbnail-safety@example.com",
			})
			require.NoError(t, err)
			creatorCtx := context.WithValue(ctx, auth.UserIDContextKey, creator.ID)
			attachment, err := svc.CreateAttachment(creatorCtx, &apiv1.CreateAttachmentRequest{
				Attachment: &apiv1.Attachment{
					Filename: "synthetic-image.png",
					Type:     test.mimeType,
					Content:  test.content,
				},
			})
			require.NoError(t, err, "preserve the existing upload fallback policy")
			_, err = svc.CreateMemo(creatorCtx, &apiv1.CreateMemoRequest{
				Memo: &apiv1.Memo{
					Content:     "synthetic thumbnail fixture",
					Visibility:  apiv1.Visibility_PUBLIC,
					Attachments: []*apiv1.Attachment{{Name: attachment.Name}},
				},
			})
			require.NoError(t, err)

			e := echo.New()
			fs.RegisterRoutes(e)
			uid := strings.TrimPrefix(attachment.Name, "attachments/")
			stored, err := svc.Store.GetAttachment(ctx, &store.FindAttachment{UID: &uid, GetBlob: true})
			require.NoError(t, err)
			require.NotNil(t, stored)
			cachePath, err := fs.getThumbnailPath(stored)
			require.NoError(t, err)

			// Exercise both first generation and repeated access, including cache hits for valid images.
			for range 2 {
				req := httptest.NewRequest(http.MethodGet,
					fmt.Sprintf("/file/%s/%s?thumbnail=true", attachment.Name, attachment.Filename), nil)
				rec := httptest.NewRecorder()
				require.NotPanics(t, func() { e.ServeHTTP(rec, req) })
				require.Equal(t, http.StatusOK, rec.Code)
				require.Equal(t, "nosniff", rec.Header().Get("X-Content-Type-Options"))
				if test.wantThumbnail {
					require.Equal(t, "image/jpeg", rec.Header().Get("Content-Type"))
					_, format, err := image.DecodeConfig(bytes.NewReader(rec.Body.Bytes()))
					require.NoError(t, err)
					require.Equal(t, "jpeg", format)
					require.FileExists(t, cachePath)
				} else {
					require.Equal(t, test.mimeType, rec.Header().Get("Content-Type"))
					require.Equal(t, test.content, rec.Body.Bytes())
					require.NoFileExists(t, cachePath)
				}
			}
			original, err := fs.getAttachmentBlob(stored)
			require.NoError(t, err)
			require.Equal(t, test.content, original, "thumbnail processing must not mutate the attachment")
		})
	}
}

// A tiny uncompressed TIFF with two palette entries. No oversized pixel buffer is allocated.
func thumbnailPalettedTIFF(pixelIndex byte, width, height uint32) []byte {
	const paletteOffset = 8 + 2 + 10*12 + 4
	var buf bytes.Buffer
	buf.WriteString("II")
	_ = binary.Write(&buf, binary.LittleEndian, uint16(42))
	_ = binary.Write(&buf, binary.LittleEndian, uint32(8))
	_ = binary.Write(&buf, binary.LittleEndian, uint16(10))
	for _, field := range []struct {
		tag, fieldType uint16
		count, value   uint32
	}{
		{256, 4, 1, width},
		{257, 4, 1, height},
		{258, 3, 1, 8},
		{259, 3, 1, 1},
		{262, 3, 1, 3},
		{273, 4, 1, paletteOffset + 12},
		{277, 3, 1, 1},
		{278, 4, 1, 1},
		{279, 4, 1, 1},
		{320, 3, 6, paletteOffset},
	} {
		_ = binary.Write(&buf, binary.LittleEndian, field)
	}
	_ = binary.Write(&buf, binary.LittleEndian, uint32(0))
	buf.Write(make([]byte, 12))
	buf.WriteByte(pixelIndex)
	return buf.Bytes()
}
