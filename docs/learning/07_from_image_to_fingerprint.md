<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# 7. From image to fingerprint

## 🧩 Keeping useful pattern information

A raw image is a pixel grid. Preprocessing makes its useful signal more
consistent. A feature extractor then describes distinctive pattern points.
The current project uses the **SIGFM** extractor and matcher on the preprocessed
80×64 raster. Its code calls the extracted points **keypoints**; they play the
role often described generally as fingerprint features. We should not casually
rename them "minutiae" or claim an unverified algorithm.

```text
sensor samples
      ↓
baseline-aware preprocessing
      ↓
80 × 64 processed image
      ↓
SIGFM feature extraction
      ↓
reusable template or new comparison sample
```

A **template** is serialized feature data used for later comparison. It is not
the original finger, and it is not merely the raw image. It is still sensitive
biometric data and must be protected.

## 🏠 A map analogy

Think of an image as an aerial photograph and a template as a map of useful
landmarks. Matching asks whether enough landmarks correspond. It does not ask
whether every pixel is identical: two touches naturally differ in pressure and
position.

The matcher produces a comparison result for libfprint. This repository makes
no broad promise about recognition accuracy, false accepts, or false rejects
across untested people and devices.

> 🔎 **Repository view:** the checked extraction and matching boundary is
> in [`goodix_sigfm_metrics.cpp`](../../libfprint-driver/goodix_sigfm_metrics.cpp).

## ✅ What to remember

- Image, features, template, and match result are different things.
- This project specifically uses SIGFM; not every fingerprint stack does.
- A template remains private even though it is not a raw photograph.

[← Previous](06_from_finger_to_image.md) · [Contents](README.md) · [Next →](08_enrollment.md)
