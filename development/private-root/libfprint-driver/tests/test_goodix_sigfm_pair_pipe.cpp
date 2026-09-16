/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Offline-only exact Rockytkg SIGFM extraction and pairwise score adapter. */
#include "sigfm.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <exception>
#include <stdexcept>

namespace {
constexpr std::size_t HeaderSize = 16;
constexpr std::size_t Pixels = 80 * 64;
constexpr std::size_t MaxSamples = 128;

struct Sample {
  SigfmImgInfo *info = nullptr;
  int keypoints = 0;
};

std::array<Sample, MaxSamples> samples;

std::uint32_t read_u32le(const unsigned char *value)
{
  return static_cast<std::uint32_t>(value[0]) |
         (static_cast<std::uint32_t>(value[1]) << 8) |
         (static_cast<std::uint32_t>(value[2]) << 16) |
         (static_cast<std::uint32_t>(value[3]) << 24);
}

void cleanse(unsigned char *data, std::size_t length)
{
  volatile unsigned char *cursor = data;
  while (length-- > 0)
    *cursor++ = 0;
}

void cleanup()
{
  for (auto &sample : samples)
    if (sample.info != nullptr)
      {
        sigfm_free_info(sample.info);
        sample.info = nullptr;
        sample.keypoints = 0;
      }
}
}

int main()
{
  unsigned char header[HeaderSize];
  try
    {
      while (true)
        {
          const std::size_t got = std::fread(header, 1, sizeof header, stdin);
          if (got == 0 && std::feof(stdin))
            break;
          if (got != sizeof header || read_u32le(&header[12]) != 0)
            throw std::runtime_error("SIGFM_PAIR_HEADER");
          const std::uint32_t first = read_u32le(&header[4]);
          const std::uint32_t second = read_u32le(&header[8]);
          if (first >= MaxSamples)
            throw std::runtime_error("SIGFM_PAIR_ID");
          if (std::memcmp(header, "SFX1", 4) == 0)
            {
              std::array<unsigned char, Pixels> image{};
              if (second != Pixels || samples[first].info != nullptr ||
                  std::fread(image.data(), 1, image.size(), stdin) != image.size())
                throw std::runtime_error("SIGFM_EXTRACT_INPUT");
              samples[first].info = sigfm_extract(image.data(), 80, 64);
              cleanse(image.data(), image.size());
              if (samples[first].info == nullptr)
                throw std::runtime_error("SIGFM_EXTRACT_NULL");
              samples[first].keypoints = sigfm_keypoints_count(samples[first].info);
              std::printf("SIGFMX %u %d %d\n", first, samples[first].keypoints,
                          samples[first].keypoints >= 25);
              std::fflush(stdout);
            }
          else if (std::memcmp(header, "SFM1", 4) == 0)
            {
              int eligible;
              int score = 0;
              if (second >= MaxSamples || samples[first].info == nullptr ||
                  samples[second].info == nullptr)
                throw std::runtime_error("SIGFM_MATCH_INPUT");
              eligible = samples[first].keypoints >= 25 &&
                         samples[second].keypoints >= 25;
              if (eligible)
                {
                  score = sigfm_match_score(samples[first].info, samples[second].info);
                  if (score < 0)
                    throw std::runtime_error("SIGFM_MATCH_ERROR");
                }
              std::printf("SIGFMM %u %u %d %d\n", first, second, eligible, score);
              std::fflush(stdout);
            }
          else
            throw std::runtime_error("SIGFM_PAIR_MAGIC");
        }
      cleanup();
      return 0;
    }
  catch (const std::exception &error)
    {
      std::fprintf(stderr, "FAIL_CLOSED %s\n", error.what());
      cleanup();
      return 3;
    }
  catch (...)
    {
      std::fputs("FAIL_CLOSED SIGFM_UNKNOWN_EXCEPTION\n", stderr);
      cleanup();
      return 3;
    }
}
