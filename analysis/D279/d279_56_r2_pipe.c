/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Host-only stdin/stdout adapter for the production D279/49 R2 preprocessor. */
#include "goodix_sigfm_preprocess.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define D279_56_PIXELS GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT
#define D279_56_U16_BYTES (D279_56_PIXELS * 2u)

static uint32_t
read_u32le (const uint8_t value[4])
{
  return (uint32_t) value[0] |
         (uint32_t) value[1] << 8 |
         (uint32_t) value[2] << 16 |
         (uint32_t) value[3] << 24;
}

static void
write_u32le (uint8_t value[4], uint32_t number)
{
  value[0] = (uint8_t) number;
  value[1] = (uint8_t) (number >> 8);
  value[2] = (uint8_t) (number >> 16);
  value[3] = (uint8_t) (number >> 24);
}

static void
cleanse (void *memory, size_t length)
{
  volatile uint8_t *cursor = memory;

  while (length-- > 0u)
    *cursor++ = 0u;
}

static int
read_exact (void *memory, size_t length)
{
  return fread (memory, 1u, length, stdin) == length ? 0 : -1;
}

static void
decode_u16le (const uint8_t *encoded, uint16_t *samples)
{
  for (size_t index = 0u; index < D279_56_PIXELS; index++)
    samples[index] = (uint16_t) encoded[index * 2u] |
                     (uint16_t) ((uint16_t) encoded[index * 2u + 1u] << 8);
}

int
main (void)
{
  uint8_t header[8];
  uint8_t response[8];
  uint8_t baseline_encoded[D279_56_U16_BYTES];
  uint8_t frame_encoded[D279_56_U16_BYTES];
  uint16_t baseline[D279_56_PIXELS];
  uint16_t frame[D279_56_PIXELS];
  uint8_t output[D279_56_PIXELS];

  while (1)
    {
      size_t got = fread (header, 1u, sizeof header, stdin);
      GoodixSigfmPreprocessResult result;

      if (got == 0u && feof (stdin))
        break;
      if (got != sizeof header || memcmp (header, "D56R", 4u) != 0 ||
          read_u32le (header + 4u) != D279_56_U16_BYTES ||
          read_exact (baseline_encoded, sizeof baseline_encoded) != 0 ||
          read_exact (frame_encoded, sizeof frame_encoded) != 0)
        {
          fputs ("FAIL_CLOSED D279_56_R2_PIPE_INPUT\n", stderr);
          return 2;
        }
      decode_u16le (baseline_encoded, baseline);
      decode_u16le (frame_encoded, frame);
      result = goodix_sigfm_preprocess_r2 (
        baseline, D279_56_PIXELS, frame, D279_56_PIXELS,
        output, sizeof output);
      if (result != GOODIX_SIGFM_PREPROCESS_OK)
        {
          fputs ("FAIL_CLOSED D279_56_R2_PREPROCESS\n", stderr);
          return 3;
        }
      memcpy (response, "D56O", 4u);
      write_u32le (response + 4u, D279_56_PIXELS);
      if (fwrite (response, 1u, sizeof response, stdout) != sizeof response ||
          fwrite (output, 1u, sizeof output, stdout) != sizeof output ||
          fflush (stdout) != 0)
        return 4;
      cleanse (baseline_encoded, sizeof baseline_encoded);
      cleanse (frame_encoded, sizeof frame_encoded);
      cleanse (baseline, sizeof baseline);
      cleanse (frame, sizeof frame);
      cleanse (output, sizeof output);
    }
  cleanse (baseline_encoded, sizeof baseline_encoded);
  cleanse (frame_encoded, sizeof frame_encoded);
  cleanse (baseline, sizeof baseline);
  cleanse (frame, sizeof frame);
  cleanse (output, sizeof output);
  return 0;
}
