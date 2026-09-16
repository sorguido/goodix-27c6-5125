/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * D279/48 host-only pipe around the exact preserved Rockytkg image pipeline.
 *
 * The processing implementation is compiled directly from:
 *   Rockytkg/src/goodix_imgproc.c
 *   upstream commit 227eba219fa9e3fbac5bd59aca79f624f67cd11b
 * That source is GPL-2.0-or-later.  This wrapper fixes the two already
 * implemented parameter sets (R1/R2), disables all environment overrides and
 * debug dumps, and exposes no device, path, secret, or USB interface.
 */

#include "goodix.h"
#include "goodix_imgproc.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HEADER_SIZE 16u
#define WIDTH 80u
#define HEIGHT 64u
#define PIXELS (WIDTH * HEIGHT)
#define U16_BYTES (PIXELS * 2u)

char *
d279_48_no_environment (const char *name)
{
  (void) name;
  return NULL;
}

const char *
gx_state_dir (void)
{
  abort ();
}

int
gx_state_dir_ensure (void)
{
  abort ();
}

static uint32_t
read_u32le (const uint8_t *value)
{
  return ((uint32_t) value[0]) |
         ((uint32_t) value[1] << 8) |
         ((uint32_t) value[2] << 16) |
         ((uint32_t) value[3] << 24);
}

static void
write_u32le (uint8_t *value, uint32_t number)
{
  value[0] = (uint8_t) number;
  value[1] = (uint8_t) (number >> 8);
  value[2] = (uint8_t) (number >> 16);
  value[3] = (uint8_t) (number >> 24);
}

static void
cleanse (uint8_t *data, size_t length)
{
  volatile uint8_t *cursor = data;
  while (length-- > 0)
    *cursor++ = 0;
}

static int
read_exact (uint8_t *buffer, size_t length)
{
  return fread (buffer, 1, length, stdin) == length ? 0 : -1;
}

static int
valid_u12le (const uint8_t *image)
{
  for (size_t i = 0; i < U16_BYTES; i += 2)
    if ((image[i + 1] & 0xf0u) != 0)
      return 0;
  return 1;
}

int
main (void)
{
  uint8_t header[HEADER_SIZE];
  uint8_t response[12];
  uint8_t baseline[U16_BYTES];
  uint8_t frame[U16_BYTES];
  uint8_t output[PIXELS];
  struct goodix_dev device;

  memset (&device, 0, sizeof device);
  device.img_w = WIDTH;
  device.img_h = HEIGHT;
  device.img_size = U16_BYTES;
  device.img_base_valid = true;

  while (1)
    {
      size_t got = fread (header, 1, sizeof header, stdin);
      uint32_t checkpoint;
      uint32_t length;
      struct gx_imgproc_params params;

      if (got == 0 && feof (stdin))
        break;
      if (got != sizeof header || memcmp (header, "RIP1", 4) != 0)
        {
          fputs ("FAIL_CLOSED ROCKY_IMGPROC_HEADER\n", stderr);
          return 2;
        }
      checkpoint = read_u32le (&header[4]);
      length = read_u32le (&header[8]);
      if ((checkpoint != 1 && checkpoint != 2) || length != U16_BYTES ||
          read_u32le (&header[12]) != 0 ||
          read_exact (baseline, sizeof baseline) != 0 ||
          read_exact (frame, sizeof frame) != 0)
        {
          fputs ("FAIL_CLOSED ROCKY_IMGPROC_INPUT\n", stderr);
          return 2;
        }
      if (!valid_u12le (baseline) || !valid_u12le (frame))
        {
          fputs ("FAIL_CLOSED ROCKY_IMGPROC_RANGE\n", stderr);
          return 2;
        }
      memcpy (device.img_base, baseline, sizeof baseline);
      if (checkpoint == 1)
        {
          const struct gx_imgproc_params fixed = GX_IMGPROC_DEFAULT_PARAMS;
          params = fixed;
        }
      else
        {
          const struct gx_imgproc_params fixed = GX_IMGPROC_SIGFM_PARAMS;
          params = fixed;
        }
      if (gx_imgproc_to8bit (&device, &params, frame, output) != 0)
        {
          fputs ("FAIL_CLOSED ROCKY_IMGPROC_EXECUTION\n", stderr);
          return 3;
        }
      memcpy (response, "RIPO", 4);
      write_u32le (&response[4], checkpoint);
      write_u32le (&response[8], PIXELS);
      if (fwrite (response, 1, sizeof response, stdout) != sizeof response ||
          fwrite (output, 1, sizeof output, stdout) != sizeof output ||
          fflush (stdout) != 0)
        return 4;
      cleanse (baseline, sizeof baseline);
      cleanse (frame, sizeof frame);
      cleanse (output, sizeof output);
      cleanse (device.img_base, sizeof baseline);
    }
  cleanse (baseline, sizeof baseline);
  cleanse (frame, sizeof frame);
  cleanse (output, sizeof output);
  cleanse (device.img_base, sizeof baseline);
  return 0;
}
