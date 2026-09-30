package v1

import (
	"bytes"
	"encoding/binary"
	"hash/crc32"
	"image"
	"image/color"
	"image/jpeg"
	"testing"

	"github.com/kovidgoyal/imaging"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestShouldStripExif(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		mimeType string
		expected bool
	}{
		{
			name:     "JPEG should strip EXIF",
			mimeType: "image/jpeg",
			expected: true,
		},
		{
			name:     "JPG should strip EXIF",
			mimeType: "image/jpg",
			expected: true,
		},
		{
			name:     "TIFF should strip EXIF",
			mimeType: "image/tiff",
			expected: true,
		},
		{
			name:     "WebP should strip EXIF",
			mimeType: "image/webp",
			expected: true,
		},
		{
			name:     "HEIC should strip EXIF",
			mimeType: "image/heic",
			expected: true,
		},
		{
			name:     "HEIF should strip EXIF",
			mimeType: "image/heif",
			expected: true,
		},
		{
			name:     "PNG should not strip EXIF",
			mimeType: "image/png",
			expected: false,
		},
		{
			name:     "GIF should not strip EXIF",
			mimeType: "image/gif",
			expected: false,
		},
		{
			name:     "text file should not strip EXIF",
			mimeType: "text/plain",
			expected: false,
		},
		{
			name:     "PDF should not strip EXIF",
			mimeType: "application/pdf",
			expected: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			result := shouldStripExif(tt.mimeType)
			assert.Equal(t, tt.expected, result)
		})
	}
}

func TestStripImageExif(t *testing.T) {
	t.Parallel()

	// Create a simple test image
	img := image.NewRGBA(image.Rect(0, 0, 100, 100))
	// Fill with red color
	for y := 0; y < 100; y++ {
		for x := 0; x < 100; x++ {
			img.Set(x, y, color.RGBA{R: 255, G: 0, B: 0, A: 255})
		}
	}

	// Encode as JPEG
	var buf bytes.Buffer
	err := jpeg.Encode(&buf, img, &jpeg.Options{Quality: 90})
	require.NoError(t, err)
	originalData := buf.Bytes()

	t.Run("strip JPEG metadata", func(t *testing.T) {
		t.Parallel()

		strippedData, err := stripImageExif(originalData, "image/jpeg")
		require.NoError(t, err)
		assert.NotEmpty(t, strippedData)

		// Verify it's still a valid image
		decodedImg, err := imaging.Decode(bytes.NewReader(strippedData))
		require.NoError(t, err)
		assert.Equal(t, 100, decodedImg.Bounds().Dx())
		assert.Equal(t, 100, decodedImg.Bounds().Dy())
	})

	t.Run("strip JPG metadata (alternate extension)", func(t *testing.T) {
		t.Parallel()

		strippedData, err := stripImageExif(originalData, "image/jpg")
		require.NoError(t, err)
		assert.NotEmpty(t, strippedData)

		// Verify it's still a valid image
		decodedImg, err := imaging.Decode(bytes.NewReader(strippedData))
		require.NoError(t, err)
		assert.NotNil(t, decodedImg)
	})

	t.Run("strip PNG metadata", func(t *testing.T) {
		t.Parallel()

		// Encode as PNG first
		var pngBuf bytes.Buffer
		err := imaging.Encode(&pngBuf, img, imaging.PNG)
		require.NoError(t, err)

		strippedData, err := stripImageExif(pngBuf.Bytes(), "image/png")
		require.NoError(t, err)
		assert.NotEmpty(t, strippedData)

		// Verify it's still a valid image
		decodedImg, err := imaging.Decode(bytes.NewReader(strippedData))
		require.NoError(t, err)
		assert.Equal(t, 100, decodedImg.Bounds().Dx())
		assert.Equal(t, 100, decodedImg.Bounds().Dy())
	})

	t.Run("handle WebP format by converting to JPEG", func(t *testing.T) {
		t.Parallel()

		// WebP format will be converted to JPEG
		strippedData, err := stripImageExif(originalData, "image/webp")
		require.NoError(t, err)
		assert.NotEmpty(t, strippedData)

		// Verify it's a valid image
		decodedImg, err := imaging.Decode(bytes.NewReader(strippedData))
		require.NoError(t, err)
		assert.NotNil(t, decodedImg)
	})

	t.Run("handle HEIC format by converting to JPEG", func(t *testing.T) {
		t.Parallel()

		strippedData, err := stripImageExif(originalData, "image/heic")
		require.NoError(t, err)
		assert.NotEmpty(t, strippedData)

		// Verify it's a valid image
		decodedImg, err := imaging.Decode(bytes.NewReader(strippedData))
		require.NoError(t, err)
		assert.NotNil(t, decodedImg)
	})

	t.Run("return error for invalid image data", func(t *testing.T) {
		t.Parallel()

		invalidData := []byte("not an image")
		_, err := stripImageExif(invalidData, "image/jpeg")
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "failed to decode image")
	})

	t.Run("return error for empty image data", func(t *testing.T) {
		t.Parallel()

		emptyData := []byte{}
		_, err := stripImageExif(emptyData, "image/jpeg")
		assert.Error(t, err)
	})
}

func TestValidateImagePixelCountRejectsOversizedDimensions(t *testing.T) {
	t.Parallel()

	err := validateImagePixelCount(testPNGHeaderWithDimensions(100_000, 100_000))
	require.Error(t, err)
	require.Contains(t, err.Error(), "image dimensions exceed maximum")
}

func TestStripImageExifRejectsOversizedDimensionsBeforeDecode(t *testing.T) {
	t.Parallel()

	_, err := stripImageExif(testPNGHeaderWithDimensions(100_000, 100_000), "image/png")
	require.Error(t, err)
	require.Contains(t, err.Error(), "image dimensions exceed maximum")
}

func TestStripImageExifRejectsPackBitsExpansionBeyondPixelBound(t *testing.T) {
	t.Parallel()

	_, err := stripImageExif(testPackBitsTIFFWithOversizedDecodedStrip(), "image/tiff")
	require.Error(t, err)
	require.Contains(t, err.Error(), "PackBits: decompressed data too large")
}

func TestStripImageExifRejectsOutOfRangeTIFFPaletteIndex(t *testing.T) {
	// GHSA-q7pp-wcgr-pffx reaches imaging's scanner with an invalid palette index.
	// Verify the decoder rejects it before image processing, with a valid control.
	valid := testPalettedTIFF(1)
	_, err := stripImageExif(valid, "image/tiff")
	require.NoError(t, err)

	_, err = stripImageExif(testPalettedTIFF(2), "image/tiff")
	require.Error(t, err)
	require.Contains(t, err.Error(), "invalid color index")
}

func testPNGHeaderWithDimensions(width, height uint32) []byte {
	var buf bytes.Buffer
	buf.Write([]byte{0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'})

	ihdr := make([]byte, 13)
	binary.BigEndian.PutUint32(ihdr[0:4], width)
	binary.BigEndian.PutUint32(ihdr[4:8], height)
	ihdr[8] = 8
	ihdr[9] = 2

	writePNGChunk(&buf, "IHDR", ihdr)
	writePNGChunk(&buf, "IEND", nil)
	return buf.Bytes()
}

func writePNGChunk(buf *bytes.Buffer, chunkType string, data []byte) {
	_ = binary.Write(buf, binary.BigEndian, uint32(len(data)))
	buf.WriteString(chunkType)
	buf.Write(data)
	crc := crc32.ChecksumIEEE(append([]byte(chunkType), data...))
	_ = binary.Write(buf, binary.BigEndian, crc)
}

func testPackBitsTIFFWithOversizedDecodedStrip() []byte {
	const (
		entryCount  = 9
		stripOffset = 8 + 2 + entryCount*12 + 4
	)

	var buf bytes.Buffer
	buf.WriteString("II")
	_ = binary.Write(&buf, binary.LittleEndian, uint16(42))
	_ = binary.Write(&buf, binary.LittleEndian, uint32(8))
	_ = binary.Write(&buf, binary.LittleEndian, uint16(entryCount))

	writeTIFFEntry := func(tag, fieldType uint16, count, value uint32) {
		_ = binary.Write(&buf, binary.LittleEndian, tag)
		_ = binary.Write(&buf, binary.LittleEndian, fieldType)
		_ = binary.Write(&buf, binary.LittleEndian, count)
		_ = binary.Write(&buf, binary.LittleEndian, value)
	}
	writeTIFFEntry(256, 3, 1, 1)           // ImageWidth: 1
	writeTIFFEntry(257, 3, 1, 1)           // ImageLength: 1
	writeTIFFEntry(258, 3, 1, 8)           // BitsPerSample: 8
	writeTIFFEntry(259, 3, 1, 32773)       // Compression: PackBits
	writeTIFFEntry(262, 3, 1, 1)           // PhotometricInterpretation: BlackIsZero
	writeTIFFEntry(273, 4, 1, stripOffset) // StripOffsets
	writeTIFFEntry(277, 3, 1, 1)           // SamplesPerPixel: 1
	writeTIFFEntry(278, 4, 1, 1)           // RowsPerStrip: 1
	writeTIFFEntry(279, 4, 1, 2)           // StripByteCounts: 2
	_ = binary.Write(&buf, binary.LittleEndian, uint32(0))
	buf.Write([]byte{0xf8, 0x00}) // Repeat one byte 9 times; patched decoder caps this 1x1 block at 8 bytes.
	return buf.Bytes()
}

func testPalettedTIFF(pixelIndex byte) []byte {
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
		{256, 3, 1, 1},                  // Width: 1
		{257, 3, 1, 1},                  // Height: 1
		{258, 3, 1, 8},                  // BitsPerSample: 8
		{259, 3, 1, 1},                  // No compression
		{262, 3, 1, 3},                  // Palette color
		{273, 4, 1, paletteOffset + 12}, // StripOffsets
		{277, 3, 1, 1},                  // SamplesPerPixel: 1
		{278, 4, 1, 1},                  // RowsPerStrip: 1
		{279, 4, 1, 1},                  // StripByteCounts: 1
		{320, 3, 6, paletteOffset},      // ColorMap: two entries per RGB channel
	} {
		_ = binary.Write(&buf, binary.LittleEndian, field)
	}
	_ = binary.Write(&buf, binary.LittleEndian, uint32(0))
	buf.Write(make([]byte, 12))
	buf.WriteByte(pixelIndex)
	return buf.Bytes()
}
