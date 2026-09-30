package fileserver

import (
	"bytes"
	"context"
	"encoding/binary"
	"fmt"
	"image"
	"image/color"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"testing/iotest"

	"github.com/kovidgoyal/imaging"
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

func TestDecodeThumbnailImagePreservesEXIFOrientation(t *testing.T) {
	source := image.NewNRGBA(image.Rect(0, 0, 2, 3))
	for y := range 3 {
		for x := range 2 {
			source.SetNRGBA(x, y, color.NRGBA{R: uint8(30 + 80*x), G: uint8(20 + 70*y), B: 100, A: 255})
		}
	}
	var encoded bytes.Buffer
	require.NoError(t, imaging.Encode(&encoded, source, imaging.JPEG, imaging.JPEGQuality(90)))
	plain, _, err := image.Decode(bytes.NewReader(encoded.Bytes()))
	require.NoError(t, err)
	for orientation := uint16(1); orientation <= 8; orientation++ {
		t.Run(fmt.Sprintf("orientation %d", orientation), func(t *testing.T) {
			// A single synthetic orientation tag; no user metadata or external files.
			exif := make([]byte, 32)
			copy(exif, "Exif\x00\x00II\x2a\x00")
			binary.LittleEndian.PutUint32(exif[10:14], 8)
			binary.LittleEndian.PutUint16(exif[14:16], 1)
			binary.LittleEndian.PutUint16(exif[16:18], 274)
			binary.LittleEndian.PutUint16(exif[18:20], 3)
			binary.LittleEndian.PutUint32(exif[20:24], 1)
			binary.LittleEndian.PutUint16(exif[24:26], orientation)
			content := append([]byte{0xff, 0xd8, 0xff, 0xe1, 0, 34}, exif...)
			content = append(content, encoded.Bytes()[2:]...)
			result, err := decodeThumbnailImage(iotest.OneByteReader(bytes.NewReader(content)))
			require.NoError(t, err)
			width, height := 2, 3
			if orientation >= 5 {
				width, height = height, width
			}
			require.Equal(t, image.Rect(0, 0, width, height), result.Bounds())
			for y := range height {
				for x := range width {
					sx, sy := x, y
					switch orientation {
					case 1:
						// The encoded image already has the desired orientation.
					case 2:
						sx = 1 - x
					case 3:
						sx, sy = 1-x, 2-y
					case 4:
						sy = 2 - y
					case 5:
						sx, sy = y, x
					case 6:
						sx, sy = y, 2-x
					case 7:
						sx, sy = 1-y, 2-x
					case 8:
						sx, sy = 1-y, x
					default:
						t.Fatalf("unsupported synthetic orientation: %d", orientation)
					}
					require.Equal(t, color.NRGBAModel.Convert(plain.At(sx, sy)), color.NRGBAModel.Convert(result.At(x, y)))
				}
			}
		})
	}
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

func TestImagingPaletteBounds(t *testing.T) {
	for _, test := range []struct {
		name      string
		index     byte
		wantAlpha uint32
	}{
		{"valid palette index", 0, 0xffff},
		{"out-of-range palette index", 255, 0},
	} {
		t.Run(test.name, func(t *testing.T) {
			img := image.NewPaletted(image.Rect(0, 0, 1, 1), color.Palette{
				color.NRGBA{R: 80, G: 120, B: 160, A: 255},
			})
			img.Pix[0] = test.index
			for name, transform := range map[string]func(image.Image) image.Image{
				"grayscale": func(src image.Image) image.Image { return imaging.Grayscale(src) },
				"resize":    func(src image.Image) image.Image { return imaging.Resize(src, 2, 2, imaging.Lanczos) },
			} {
				t.Run(name, func(t *testing.T) {
					result := transform(img)
					require.NotNil(t, result)
					_, _, _, alpha := result.At(0, 0).RGBA()
					require.Equal(t, test.wantAlpha, alpha)
				})
			}
		})
	}
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
