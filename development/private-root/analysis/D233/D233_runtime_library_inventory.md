# D233 runtime library inventory

Inventory performed on 2026-08-14 without USB enumeration, initialization or
device access.

| Component | Local result | Selected use |
| --- | --- | --- |
| libusb-1.0 | runtime `libusb-1.0.so.0` in `/lib64` and `/lib`; no header or pkg-config metadata | minimal `ctypes` ABI binding, source-sealed before every libusb call |
| OpenSSL | 3.5.7, headers and pkg-config present | Python `ssl.MemoryBIO` TLS engine backed by system OpenSSL |
| Python ssl | Python 3.14.6; `SSLContext.set_psk_server_callback=true` | TLS 1.2 PSK server and loopback tests |
| cryptography | already installed; AES/AESGCM imports pass | recovered D190 clean-room reference only |
| mbedTLS | no pkg-config package found | not selected |
| compiler | GCC 16.1.1 | syntax/toolchain inventory only; no native helper needed |

Symbol inspection confirmed the exact libusb ABI surface used by the source:
`libusb_init/exit`, exact VID/PID open, descriptor/device/bus/address/port
identity, claim/release, bulk transfer and close. `libssl.so.3` exports
`SSL_CTX_set_psk_server_callback` and `SSL_do_handshake`. The configured
TLS-1.2 cipher list contains exactly `PSK-AES128-GCM-SHA256` after filtering
out TLS-1.3 ciphers, which are disabled by min/max version.

The udev rule `/etc/udev/rules.d/70-goodix-5125.rules` was absent. No package
manager or installer was used.
