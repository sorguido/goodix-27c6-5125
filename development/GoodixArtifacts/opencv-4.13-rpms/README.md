<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Pinned OpenCV RPM inputs

The production build expects five Fedora 44 OpenCV 4.13.0 RPMs in this
directory. RPM payloads are not stored in Git; download them from Fedora:

```bash
dnf5 download --destdir GoodixArtifacts/opencv-4.13-rpms \
  opencv-core-4.13.0-1.fc44.x86_64 \
  opencv-devel-4.13.0-1.fc44.x86_64 \
  opencv-features2d-4.13.0-1.fc44.x86_64 \
  opencv-flann-4.13.0-1.fc44.x86_64 \
  opencv-imgproc-4.13.0-1.fc44.x86_64
(cd GoodixArtifacts/opencv-4.13-rpms && \
  sha256sum -c ../../production/build-support/opencv-rpms.sha256)
```

Do not substitute another version or edit the digest manifest to accept a
different package set. The build extracts headers, libraries, and license files
without installing these RPMs on the host.
