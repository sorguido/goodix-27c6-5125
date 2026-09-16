<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# OpenCV 4.13 RPM locali

Questa è la directory locale persistente canonica per i cinque RPM OpenCV
Fedora 44 usati dai kit Goodix:

```text
/home/guido/Repository/goodix-27c6-5125_private/GoodixArtifacts/opencv-4.13-rpms
```

I payload `.rpm` sono intenzionalmente ignorati da Git. Nomi e SHA-256 restano
definiti esclusivamente dal manifest versionato:

```text
operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256
```

Verifica dalla root del repository:

```bash
cd GoodixArtifacts/opencv-4.13-rpms
sha256sum -c ../../operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256
```

Una directory vuota o un digest diverso è un gate fail-closed. Non cambiare il
manifest per adattarlo a RPM differenti senza nuova evidenza tecnica.
