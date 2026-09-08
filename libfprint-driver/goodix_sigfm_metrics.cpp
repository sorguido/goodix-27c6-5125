/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_sigfm_metrics.h"

#include "goodix_u16_to_fpimage.h"
#include "sigfm.h"

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>
#include <type_traits>

struct GoodixSigfmSample
{
  SigfmImgInfo *info;
};

namespace
{
constexpr size_t kPixelCount = GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT;
constexpr size_t kEnvelopeSize = 24;
constexpr size_t kRockyFixedSize = 20;
constexpr size_t kRockyBytesPerKeypoint = 540;
constexpr uint32_t kEndianMarker = UINT32_C (0x01020304);
constexpr uint32_t kOpenCv32Fc1 = 5;
constexpr uint32_t kSiftDescriptorColumns = 128;

static_assert (sizeof (size_t) == 8, "SIGFM storage requires x86_64 size_t");
static_assert (sizeof (int) == 4, "SIGFM storage requires 32-bit int");
static_assert (sizeof (float) == 4, "SIGFM storage requires IEEE binary32");

uint16_t
read_u16le (const uint8_t *value)
{
  return static_cast<uint16_t> (value[0]) |
         static_cast<uint16_t> (static_cast<uint16_t> (value[1]) << 8);
}

uint32_t
read_u32le (const uint8_t *value)
{
  return static_cast<uint32_t> (value[0]) |
         (static_cast<uint32_t> (value[1]) << 8) |
         (static_cast<uint32_t> (value[2]) << 16) |
         (static_cast<uint32_t> (value[3]) << 24);
}

uint64_t
read_u64le (const uint8_t *value)
{
  uint64_t result = 0;

  for (unsigned int i = 0; i < 8; i++)
    result |= static_cast<uint64_t> (value[i]) << (8u * i);
  return result;
}

float
read_float32le (const uint8_t *value)
{
  uint32_t bits = read_u32le (value);
  float result;

  std::memcpy (&result, &bits, sizeof result);
  return result;
}

void
write_u16le (uint8_t *value,
             uint16_t number)
{
  value[0] = static_cast<uint8_t> (number);
  value[1] = static_cast<uint8_t> (number >> 8);
}

void
write_u32le (uint8_t *value,
             uint32_t number)
{
  value[0] = static_cast<uint8_t> (number);
  value[1] = static_cast<uint8_t> (number >> 8);
  value[2] = static_cast<uint8_t> (number >> 16);
  value[3] = static_cast<uint8_t> (number >> 24);
}

uint32_t
crc32_ieee (const uint8_t *data,
            size_t         size)
{
  uint32_t crc = UINT32_MAX;

  for (size_t i = 0; i < size; i++)
    {
      crc ^= data[i];
      for (unsigned int bit = 0; bit < 8; bit++)
        crc = (crc >> 1) ^
              (UINT32_C (0xedb88320) &
               static_cast<uint32_t> (-static_cast<int32_t> (crc & 1u)));
    }
  return ~crc;
}

bool
host_abi_supported ()
{
  const uint32_t marker = kEndianMarker;
  const auto *bytes = reinterpret_cast<const uint8_t *> (&marker);

  return bytes[0] == 0x04 && bytes[1] == 0x03 &&
         bytes[2] == 0x02 && bytes[3] == 0x01;
}

bool
keypoints_valid (int keypoints)
{
  return keypoints >= GOODIX_SIGFM_MIN_KEYPOINTS &&
         keypoints <= GOODIX_SIGFM_MAX_KEYPOINTS;
}

bool
rocky_payload_valid (const uint8_t *payload,
                     size_t         size,
                     uint32_t       keypoints)
{
  size_t matrix_header;
  size_t expected;

  if (payload == nullptr ||
      keypoints < GOODIX_SIGFM_MIN_KEYPOINTS ||
      keypoints > GOODIX_SIGFM_MAX_KEYPOINTS)
    return false;
  expected = kRockyFixedSize +
             static_cast<size_t> (keypoints) * kRockyBytesPerKeypoint;
  if (size != expected || read_u64le (payload) != keypoints)
    return false;
  for (uint32_t i = 0; i < keypoints; i++)
    {
      const uint8_t *point = &payload[8u + static_cast<size_t> (i) * 28u];
      const float angle = read_float32le (&point[4]);
      const float response = read_float32le (&point[12]);
      const float scale = read_float32le (&point[16]);
      const float x = read_float32le (&point[20]);
      const float y = read_float32le (&point[24]);

      if (!std::isfinite (angle) || angle < -1.0f || angle > 360.0f ||
          !std::isfinite (response) || !std::isfinite (scale) ||
          scale <= 0.0f || !std::isfinite (x) || !std::isfinite (y) ||
          x < 0.0f || x >= static_cast<float> (GOODIX_CANONICAL_IMAGE_WIDTH) ||
          y < 0.0f || y >= static_cast<float> (GOODIX_CANONICAL_IMAGE_HEIGHT))
        return false;
    }
  matrix_header = 8u + static_cast<size_t> (keypoints) * 28u;
  if (read_u32le (&payload[matrix_header]) != kOpenCv32Fc1 ||
      read_u32le (&payload[matrix_header + 4u]) != keypoints ||
      read_u32le (&payload[matrix_header + 8u]) != kSiftDescriptorColumns)
    return false;
  for (size_t offset = matrix_header + 12u; offset < size; offset += 4u)
    if (!std::isfinite (read_float32le (&payload[offset])))
      return false;
  return true;
}

void
free_info_noexcept (SigfmImgInfo *info)
{
  if (info == nullptr)
    return;
  try
    {
      sigfm_free_info (info);
    }
  catch (...)
    {
    }
}

GoodixSigfmResult
wrap_info (SigfmImgInfo        *info,
           GoodixSigfmSample **sample_out,
           int                *keypoints_out,
           GoodixSigfmResult   exception_result)
{
  GoodixSigfmSample *result;
  int keypoints;

  if (info == nullptr)
    return GOODIX_SIGFM_EXTRACT_NULL;
  try
    {
      keypoints = sigfm_keypoints_count (info);
    }
  catch (...)
    {
      free_info_noexcept (info);
      return exception_result;
    }
  if (!keypoints_valid (keypoints))
    {
      free_info_noexcept (info);
      return GOODIX_SIGFM_KEYPOINT_GATE_FAILED;
    }
  result = new (std::nothrow) GoodixSigfmSample { info };
  if (result == nullptr)
    {
      free_info_noexcept (info);
      return GOODIX_SIGFM_EXTRACT_NULL;
    }
  *sample_out = result;
  *keypoints_out = keypoints;
  return GOODIX_SIGFM_OK;
}
} // namespace

static void
secure_clear (uint8_t *buffer, size_t length)
{
  volatile uint8_t *cursor = buffer;
  while (length-- > 0)
    *cursor++ = 0;
}

GoodixSigfmResult
goodix_sigfm_extract_ephemeral (const uint16_t      *samples,
                                size_t               sample_count,
                                GoodixSigfmSample  **sample_out,
                                int                 *keypoints_out)
{
  uint8_t pixels[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  GoodixLibfprintImageMetadata metadata = {};
  GoodixU16ToFpImageResult mapped;
  GoodixSigfmResult result;

  if (samples == nullptr || sample_out == nullptr || keypoints_out == nullptr)
    return GOODIX_SIGFM_INVALID_ARGUMENT;

  *sample_out = nullptr;
  *keypoints_out = 0;
  mapped = goodix_u16_to_fpimage (samples, sample_count, pixels,
                                  sizeof pixels, &metadata);
  if (mapped != GOODIX_U16_TO_FPIMAGE_OK)
    {
      secure_clear (pixels, sizeof pixels);
      return GOODIX_SIGFM_MAPPING_FAILURE;
    }

  try
    {
      SigfmImgInfo *info = sigfm_extract (
        pixels, static_cast<int> (metadata.width),
        static_cast<int> (metadata.height));
      secure_clear (pixels, sizeof pixels);
      result = wrap_info (info, sample_out, keypoints_out,
                          GOODIX_SIGFM_EXTRACT_EXCEPTION);
    }
  catch (...)
    {
      secure_clear (pixels, sizeof pixels);
      return GOODIX_SIGFM_EXTRACT_EXCEPTION;
    }
  return result;
}

GoodixSigfmResult
goodix_sigfm_extract_pixels (const uint8_t       *pixels,
                             size_t               pixel_count,
                             GoodixSigfmSample  **sample_out,
                             int                 *keypoints_out)
{
  if (pixels == nullptr || sample_out == nullptr || keypoints_out == nullptr ||
      pixel_count != kPixelCount)
    return GOODIX_SIGFM_INVALID_ARGUMENT;
  *sample_out = nullptr;
  *keypoints_out = 0;
  try
    {
      SigfmImgInfo *info = sigfm_extract (
        pixels, static_cast<int> (GOODIX_CANONICAL_IMAGE_WIDTH),
        static_cast<int> (GOODIX_CANONICAL_IMAGE_HEIGHT));
      return wrap_info (info, sample_out, keypoints_out,
                        GOODIX_SIGFM_EXTRACT_EXCEPTION);
    }
  catch (...)
    {
      return GOODIX_SIGFM_EXTRACT_EXCEPTION;
    }
}

GoodixSigfmResult
goodix_sigfm_match_ephemeral (GoodixSigfmSample *frame,
                              GoodixSigfmSample *enrolled,
                              int               *score_out)
{
  int score;
  if (frame == nullptr || enrolled == nullptr || score_out == nullptr ||
      frame->info == nullptr || enrolled->info == nullptr)
    return GOODIX_SIGFM_INVALID_ARGUMENT;

  *score_out = 0;
  try
    {
      score = sigfm_match_score (frame->info, enrolled->info);
    }
  catch (...)
    {
      return GOODIX_SIGFM_MATCH_EXCEPTION;
    }
  if (score < 0)
    return GOODIX_SIGFM_MATCH_ERROR;
  *score_out = score;
  return GOODIX_SIGFM_OK;
}

GoodixSigfmResult
goodix_sigfm_sample_copy (const GoodixSigfmSample  *source,
                          GoodixSigfmSample       **copy_out)
{
  SigfmImgInfo *copy;
  int ignored_keypoints = 0;

  if (source == nullptr || source->info == nullptr || copy_out == nullptr)
    return GOODIX_SIGFM_INVALID_ARGUMENT;
  *copy_out = nullptr;
  try
    {
      copy = sigfm_copy_info (source->info);
      return wrap_info (copy, copy_out, &ignored_keypoints,
                        GOODIX_SIGFM_COPY_EXCEPTION);
    }
  catch (...)
    {
      return GOODIX_SIGFM_COPY_EXCEPTION;
    }
}

GoodixSigfmResult
goodix_sigfm_sample_serialize (const GoodixSigfmSample  *sample,
                               uint8_t                 **data_out,
                               size_t                   *size_out)
{
  unsigned char *payload = nullptr;
  uint8_t *result = nullptr;
  int payload_size = 0;
  int keypoints;

  if (sample == nullptr || sample->info == nullptr || data_out == nullptr ||
      size_out == nullptr)
    return GOODIX_SIGFM_INVALID_ARGUMENT;
  *data_out = nullptr;
  *size_out = 0;
  if (!host_abi_supported ())
    return GOODIX_SIGFM_UNSUPPORTED_HOST_ABI;
  try
    {
      keypoints = sigfm_keypoints_count (sample->info);
      if (!keypoints_valid (keypoints))
        return GOODIX_SIGFM_SERIALIZE_INVALID;
      payload = sigfm_serialize_binary (sample->info, &payload_size);
      if (payload == nullptr || payload_size <= 0 ||
          !rocky_payload_valid (payload, static_cast<size_t> (payload_size),
                                static_cast<uint32_t> (keypoints)))
        {
          std::free (payload);
          return GOODIX_SIGFM_SERIALIZE_INVALID;
        }
      result = static_cast<uint8_t *> (
        std::malloc (kEnvelopeSize + static_cast<size_t> (payload_size)));
      if (result == nullptr)
        {
          std::free (payload);
          return GOODIX_SIGFM_SERIALIZE_INVALID;
        }
      std::memcpy (result, "GSF1", 4);
      write_u16le (&result[4], 1);
      write_u16le (&result[6], static_cast<uint16_t> (kEnvelopeSize));
      write_u32le (&result[8], kEndianMarker);
      write_u32le (&result[12], static_cast<uint32_t> (keypoints));
      write_u32le (&result[16], static_cast<uint32_t> (payload_size));
      write_u32le (&result[20], crc32_ieee (
        payload, static_cast<size_t> (payload_size)));
      std::memcpy (&result[kEnvelopeSize], payload,
                   static_cast<size_t> (payload_size));
      secure_clear (payload, static_cast<size_t> (payload_size));
      std::free (payload);
    }
  catch (...)
    {
      if (payload != nullptr && payload_size > 0)
        secure_clear (payload, static_cast<size_t> (payload_size));
      std::free (payload);
      std::free (result);
      return GOODIX_SIGFM_SERIALIZE_EXCEPTION;
    }

  *data_out = result;
  *size_out = kEnvelopeSize + static_cast<size_t> (payload_size);
  return GOODIX_SIGFM_OK;
}

GoodixSigfmResult
goodix_sigfm_sample_deserialize (const uint8_t       *data,
                                 size_t               size,
                                 GoodixSigfmSample  **sample_out,
                                 int                 *keypoints_out)
{
  const uint8_t *payload;
  SigfmImgInfo *info = nullptr;
  unsigned char *canonical = nullptr;
  uint32_t keypoints;
  uint32_t payload_size;
  int canonical_size = 0;
  GoodixSigfmResult result;

  if (data == nullptr || sample_out == nullptr || keypoints_out == nullptr)
    return GOODIX_SIGFM_INVALID_ARGUMENT;
  *sample_out = nullptr;
  *keypoints_out = 0;
  if (!host_abi_supported ())
    return GOODIX_SIGFM_UNSUPPORTED_HOST_ABI;
  if (size < kEnvelopeSize || size > GOODIX_SIGFM_MAX_SERIALIZED_SIZE ||
      std::memcmp (data, "GSF1", 4) != 0 || read_u16le (&data[4]) != 1 ||
      read_u16le (&data[6]) != kEnvelopeSize ||
      read_u32le (&data[8]) != kEndianMarker)
    return GOODIX_SIGFM_DESERIALIZE_INVALID;
  keypoints = read_u32le (&data[12]);
  payload_size = read_u32le (&data[16]);
  if (payload_size != size - kEnvelopeSize)
    return GOODIX_SIGFM_DESERIALIZE_INVALID;
  payload = &data[kEnvelopeSize];
  if (crc32_ieee (payload, payload_size) != read_u32le (&data[20]) ||
      !rocky_payload_valid (payload, payload_size, keypoints) ||
      payload_size > static_cast<uint32_t> (std::numeric_limits<int>::max ()))
    return GOODIX_SIGFM_DESERIALIZE_INVALID;

  try
    {
      info = sigfm_deserialize_binary (payload, static_cast<int> (payload_size));
      if (info == nullptr || sigfm_keypoints_count (info) !=
                             static_cast<int> (keypoints))
        {
          free_info_noexcept (info);
          return GOODIX_SIGFM_DESERIALIZE_INVALID;
        }
      canonical = sigfm_serialize_binary (info, &canonical_size);
      if (canonical == nullptr || canonical_size != static_cast<int> (payload_size) ||
          std::memcmp (canonical, payload, payload_size) != 0)
        {
          if (canonical != nullptr && canonical_size > 0)
            secure_clear (canonical, static_cast<size_t> (canonical_size));
          std::free (canonical);
          free_info_noexcept (info);
          return GOODIX_SIGFM_DESERIALIZE_INVALID;
        }
      secure_clear (canonical, static_cast<size_t> (canonical_size));
      std::free (canonical);
      canonical = nullptr;
      result = wrap_info (info, sample_out, keypoints_out,
                          GOODIX_SIGFM_DESERIALIZE_EXCEPTION);
    }
  catch (...)
    {
      if (canonical != nullptr && canonical_size > 0)
        secure_clear (canonical, static_cast<size_t> (canonical_size));
      std::free (canonical);
      if (info != nullptr)
        {
          try
            {
              free_info_noexcept (info);
            }
          catch (...)
            {
            }
        }
      return GOODIX_SIGFM_DESERIALIZE_EXCEPTION;
    }
  return result;
}

void
goodix_sigfm_serialized_free (uint8_t *data,
                              size_t   size)
{
  if (data == nullptr)
    return;
  secure_clear (data, size);
  std::free (data);
}

void
goodix_sigfm_sample_free (GoodixSigfmSample *sample)
{
  if (sample == nullptr)
    return;
  if (sample->info != nullptr)
    {
      try
        {
          sigfm_free_info (sample->info);
        }
      catch (...)
        {
        }
      sample->info = nullptr;
    }
  delete sample;
}
