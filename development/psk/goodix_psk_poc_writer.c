// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Goodix 27c6:5125 PSK provisioning PoC — single-write gated experiment
 *
 * Safety properties:
 *   - exact USB target: 27c6:5125 only
 *   - exact firmware: GF_ST411SEC_APP_12509 only
 *   - exact pre-write pairing-E baseline required:
 *       BB010002 length 332 + pinned SHA-256
 *       BB020003 exact pinned 32-byte value
 *   - no arbitrary command interface
 *   - forbidden persistent controls are absent:
 *       A2, A4, A6, 80, 90, F0, F4
 *   - only one logical E0 write is permitted per process
 *   - no E0 retry
 *   - post-write checks:
 *       exact OEM E0 ACK followed by E0 or E2 success result
 *       BB010002 unchanged
 *       BB020003 == SHA256(BB010003)
 *       immediate TLS 1.2 PSK handshake
 *   - generated PSK is never printed and never persisted
 *   - no core dumps
 *
 * Default invocation is preflight-only. Commit requires BOTH:
 *   --commit
 *   --confirm WRITE_ONE_PSK_27C6_5125_APP12509
 */

#define _POSIX_C_SOURCE 200809L

#include <libusb-1.0/libusb.h>

#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/hmac.h>
#include <openssl/rand.h>
#include <openssl/ssl.h>

#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

#include "goodix_psk_response.h"

#define VID 0x27c6u
#define PID 0x5125u

#define IFACE_COMM 0
#define IFACE_DATA 1
#define EP_OUT 0x01u
#define EP_IN  0x81u

#define CTRL_A8 0xA8u
#define CTRL_E4 0xE4u
#define CTRL_E0 0xE0u
#define CTRL_D1 0xD1u
#define CTRL_ACK 0xB0u

#define DT_BB010002 0xBB010002u
#define DT_BB010003 0xBB010003u
#define DT_BB020003 0xBB020003u

#define BB2_LEN 332u
#define WB_LEN 102u
#define E0_BODY_LEN 452u
#define E0_FRAME_LEN 460u

#define MAX_FRAME 2048u
#define USB_CHUNK 64u

#define CONFIRM_PHRASE "WRITE_ONE_PSK_27C6_5125_APP12509"
#define TLS_IDENTITY "Client_identity"

static const uint8_t FW_EXPECTED[] = "GF_ST411SEC_APP_12509";

static const uint8_t BB010002_E_SHA256[32] = {
    0xa7,0x7e,0x1a,0x3d,0x59,0x1f,0xee,0x18,
    0xf8,0x74,0xce,0x7e,0xc3,0x20,0x9e,0xa8,
    0x76,0x5f,0x12,0x3d,0xbf,0x67,0x3c,0x29,
    0x76,0x55,0xc0,0x3c,0x96,0xe5,0x1c,0x8f
};

static const uint8_t EXPECTED_BB020003_E[32] = {
    0xd5,0xeb,0x3b,0x43,0xb1,0x8b,0x3c,0xb4,
    0x0a,0x96,0x2c,0x51,0x9e,0x20,0x47,0x17,
    0x99,0x28,0x51,0xdf,0xfa,0xa7,0xf3,0x81,
    0x66,0x7a,0xe2,0x95,0xfc,0x52,0x48,0x85
};

static const uint8_t WB_KDF_KEY[32] = {
    0x5C,0xBA,0x6E,0x25,0x81,0x95,0x18,0xDE,
    0x2D,0x53,0xE9,0x6D,0xC0,0x34,0x7A,0xB0,
    0xD4,0x27,0xD4,0x08,0x4B,0xDA,0x4F,0xAE,
    0x1B,0xFF,0x2B,0x09,0x11,0x2A,0x57,0xE5
};

static const uint8_t WB_GCM_AAD[16] = {
    0x52,0x2D,0xC1,0xF0,0x99,0x56,0x7D,0x07,
    0xF4,0x7F,0x37,0xA3,0x2A,0x84,0x42,0x7D
};

static const uint8_t WB_TEST_VECTOR_SHA256[32] = {
    0xd1,0xba,0x9a,0x47,0x90,0xf8,0xd4,0x7b,
    0xa8,0xb5,0x00,0x43,0xd7,0x2b,0x57,0x7c,
    0xdc,0x2d,0x1b,0x70,0x1d,0x46,0x61,0x97,
    0xaa,0x74,0x1a,0x94,0xfd,0x0f,0x1e,0xc4
};

struct usb_guard {
    libusb_context *ctx;
    libusb_device_handle *h;
    int detached_comm;
    int detached_data;
    int claimed_comm;
    int claimed_data;
};

struct tls_secret {
    uint8_t psk[32];
    int used;
};

static volatile sig_atomic_t write_critical = 0;

enum stage_status {
    STAGE_NOT_ATTEMPTED = 0,
    STAGE_PASS,
    STAGE_FAIL,
};

static const char *stage_status_name(enum stage_status status)
{
    switch (status) {
    case STAGE_NOT_ATTEMPTED:
        return "NOT_ATTEMPTED";
    case STAGE_PASS:
        return "PASS";
    case STAGE_FAIL:
        return "FAIL";
    }

    return "INVALID";
}

static void signal_handler(int sig)
{
    if (write_critical) {
        static const char msg[] =
            "\nSIGNAL_DEFERRED_DURING_WRITE_CRITICAL_SECTION=YES\n";
        (void)!write(STDERR_FILENO, msg, sizeof(msg) - 1u);
        return;
    }
    _exit(128 + sig);
}

static int64_t monotonic_ms(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0)
        return -1;
    return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static int sleep_10ms(void)
{
    struct timespec delay = {0, 10 * 1000 * 1000};

    while (nanosleep(&delay, &delay) != 0) {
        if (errno != EINTR)
            return -1;
    }

    return 0;
}

static void put_le32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static uint32_t get_le32(const uint8_t *p)
{
    return (uint32_t)p[0] |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static uint16_t get_le16(const uint8_t *p)
{
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static int sha256_buf(const uint8_t *data, size_t len, uint8_t out[32])
{
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    unsigned int n = 0;
    int ok;

    if (!ctx)
        return -1;

    ok = EVP_DigestInit_ex(ctx, EVP_sha256(), NULL) == 1 &&
         EVP_DigestUpdate(ctx, data, len) == 1 &&
         EVP_DigestFinal_ex(ctx, out, &n) == 1 &&
         n == 32;

    EVP_MD_CTX_free(ctx);
    return ok ? 0 : -1;
}

static uint8_t a0_checksum_with_coordinate(uint8_t checksum_control,
                                            const uint8_t *body,
                                            size_t body_len)
{
    uint16_t inner_len = (uint16_t)(body_len + 1u);
    unsigned int sum =
        (unsigned int)checksum_control +
        (uint8_t)inner_len +
        (uint8_t)(inner_len >> 8);

    for (size_t i = 0; i < body_len; ++i)
        sum += body[i];

    return (uint8_t)(0xAAu - sum);
}

static uint8_t a0_checksum(uint8_t control,
                           const uint8_t *body,
                           size_t body_len)
{
    return a0_checksum_with_coordinate(control, body, body_len);
}

static int validate_a0_frame(const uint8_t *f, size_t n)
{
    uint16_t payload_len, inner_len;
    size_t body_len;

    if (!f || n < 8 || f[0] != 0xA0)
        return -1;

    payload_len = get_le16(f + 1);
    if ((size_t)payload_len + 4u != n)
        return -1;

    if (f[3] != (uint8_t)(f[0] + f[1] + f[2]))
        return -1;

    inner_len = get_le16(f + 5);
    if (inner_len == 0 || (size_t)inner_len + 3u != payload_len)
        return -1;

    body_len = (size_t)inner_len - 1u;

    if (f[n - 1u] != a0_checksum(f[4], f + 7, body_len))
        return -1;

    return 0;
}

static int validate_b0_frame(const uint8_t *f, size_t n)
{
    uint16_t payload_len;

    if (!f || n < 5 || f[0] != 0xB0)
        return -1;

    payload_len = get_le16(f + 1);
    if ((size_t)payload_len + 4u != n)
        return -1;

    if (f[3] != (uint8_t)(f[0] + f[1] + f[2]))
        return -1;

    return 0;
}

static int usb_bulk_write64(libusb_device_handle *h,
                            const uint8_t block[USB_CHUNK])
{
    int transferred = 0;
    int r = libusb_bulk_transfer(h, EP_OUT, (unsigned char *)block,
                                 USB_CHUNK, &transferred, 1000);
    if (r != 0 || transferred != (int)USB_CHUNK)
        return -1;
    return 0;
}

static int send_padded_frame(libusb_device_handle *h,
                             const uint8_t *frame,
                             size_t frame_len)
{
    size_t off = 0;

    while (off < frame_len) {
        uint8_t block[USB_CHUNK] = {0};
        size_t n = frame_len - off;

        if (n > USB_CHUNK)
            n = USB_CHUNK;

        memcpy(block, frame + off, n);

        if (usb_bulk_write64(h, block) != 0)
            return -1;

        off += n;
    }

    return 0;
}

static int read_one_frame(libusb_device_handle *h,
                          uint8_t *frame,
                          size_t cap,
                          int timeout_ms,
                          size_t *out_len)
{
    uint8_t block[USB_CHUNK];
    size_t have = 0, total = 0;
    int64_t deadline = monotonic_ms() + timeout_ms;

    if (deadline < 0)
        return -1;

    for (;;) {
        int64_t now = monotonic_ms();
        int remaining;
        int transferred = 0;
        int r;

        if (now < 0 || now >= deadline)
            return -1;

        remaining = (int)(deadline - now);
        if (remaining > 100)
            remaining = 100;
        if (remaining < 1)
            remaining = 1;

        r = libusb_bulk_transfer(h, EP_IN, block, sizeof(block),
                                 &transferred, remaining);

        if (r == LIBUSB_ERROR_TIMEOUT)
            continue;
        if (r != 0)
            return -1;
        if (transferred < 4)
            continue;

        if ((block[0] & 0xF0u) != 0xA0u &&
            (block[0] & 0xF0u) != 0xB0u &&
            (block[0] & 0xF0u) != 0xC0u)
            continue;

        if (block[3] != (uint8_t)(block[0] + block[1] + block[2]))
            continue;

        total = (size_t)get_le16(block + 1) + 4u;

        if (total < 4u || total > cap)
            return -1;

        {
            size_t first = (size_t)transferred;
            if (first > total)
                first = total;
            memcpy(frame, block, first);
            have = first;
        }

        while (have < total) {
            now = monotonic_ms();
            if (now < 0 || now >= deadline)
                return -1;

            remaining = (int)(deadline - now);
            if (remaining > 100)
                remaining = 100;
            if (remaining < 1)
                remaining = 1;

            transferred = 0;
            r = libusb_bulk_transfer(h, EP_IN, block, sizeof(block),
                                     &transferred, remaining);

            if (r == LIBUSB_ERROR_TIMEOUT)
                continue;
            if (r != 0)
                return -1;
            if (transferred <= 0)
                continue;

            {
                size_t n = (size_t)transferred;
                if (n > total - have)
                    n = total - have;
                memcpy(frame + have, block, n);
                have += n;
            }
        }

        *out_len = total;
        return 0;
    }
}

static int send_nop(libusb_device_handle *h)
{
    static const uint8_t nop[12] = {
        0xA0,0x08,0x00,0xA8,0x01,0x05,0x00,
        0x00,0x00,0x00,0x00,0x88
    };
    return send_padded_frame(h, nop, sizeof(nop));
}

static int build_and_send_read_control(libusb_device_handle *h,
                                       uint8_t control,
                                       const uint8_t *body,
                                       size_t body_len)
{
    uint8_t frame[64] = {0};
    uint16_t payload_len, inner_len;
    size_t total;

    if (control != CTRL_A8 && control != CTRL_E4)
        return -100;

    if (body_len > 48u)
        return -1;

    inner_len = (uint16_t)(body_len + 1u);
    payload_len = (uint16_t)(body_len + 4u);
    total = (size_t)payload_len + 4u;

    frame[0] = 0xA0;
    frame[1] = (uint8_t)payload_len;
    frame[2] = (uint8_t)(payload_len >> 8);
    frame[3] = (uint8_t)(frame[0] + frame[1] + frame[2]);
    frame[4] = control;
    frame[5] = (uint8_t)inner_len;
    frame[6] = (uint8_t)(inner_len >> 8);

    if (body_len)
        memcpy(frame + 7, body, body_len);

    frame[7 + body_len] = a0_checksum(control, body, body_len);

    return send_padded_frame(h, frame, total);
}

static int wait_typed_response(libusb_device_handle *h,
                               uint8_t expected_control,
                               uint8_t *body_out,
                               size_t body_cap,
                               size_t *body_len_out)
{
    int ack_seen = 0;
    int64_t deadline = monotonic_ms() + 6000;

    while (monotonic_ms() < deadline) {
        uint8_t frame[MAX_FRAME];
        size_t n = 0;
        size_t body_len;
        const uint8_t *body;
        uint8_t control;

        if (read_one_frame(h, frame, sizeof(frame), 500, &n) != 0)
            continue;

        if ((frame[0] & 0xF0u) != 0xA0u)
            continue;

        if (validate_a0_frame(frame, n) != 0)
            return -1;

        body_len = (size_t)get_le16(frame + 5) - 1u;
        body = frame + 7;
        control = frame[4];

        if (control == CTRL_ACK) {
            if (body_len != 2u)
                return -1;

            /* A duplicate ACK from the preceding transaction is late data. */
            if (body[0] != expected_control)
                continue;

            if (body[1] != 0x01u && body[1] != 0x07u)
                return -1;

            ack_seen = 1;
            continue;
        }

        if (control != expected_control)
            continue;

        if (!ack_seen)
            return -1;

        if (body_len > body_cap)
            return -1;

        memcpy(body_out, body, body_len);
        *body_len_out = body_len;
        return 0;
    }

    return -1;
}

static int read_firmware(libusb_device_handle *h)
{
    uint8_t req[2] = {0,0};
    uint8_t body[128];
    size_t body_len = 0;

    if (send_nop(h) != 0)
        return -1;

    if (sleep_10ms() != 0)
        return -1;

    if (build_and_send_read_control(h, CTRL_A8, req, sizeof(req)) != 0)
        return -1;

    if (wait_typed_response(h, CTRL_A8, body, sizeof(body), &body_len) != 0)
        return -1;

    if (body_len != sizeof(FW_EXPECTED) ||
        CRYPTO_memcmp(body, FW_EXPECTED, sizeof(FW_EXPECTED)) != 0)
        return -2;

    return 0;
}

static int e4_read(libusb_device_handle *h,
                   uint32_t dtype,
                   uint8_t *payload,
                   size_t payload_cap,
                   size_t *payload_len)
{
    uint8_t req[8] = {0};
    uint8_t body[1024];
    size_t body_len = 0;
    uint32_t response_type, declared_len;

    put_le32(req, dtype);

    if (build_and_send_read_control(h, CTRL_E4, req, sizeof(req)) != 0)
        return -1;

    if (wait_typed_response(h, CTRL_E4, body, sizeof(body), &body_len) != 0)
        return -1;

    if (body_len < 9u)
        return -1;

    if (body[0] != 0x00u)
        return -2;

    response_type = get_le32(body + 1);
    declared_len = get_le32(body + 5);

    if (response_type != dtype)
        return -3;

    if ((size_t)declared_len != body_len - 9u ||
        declared_len > payload_cap)
        return -4;

    memcpy(payload, body + 9, declared_len);
    *payload_len = declared_len;

    return 0;
}

static int detach_and_claim(libusb_device_handle *h,
                            int iface,
                            int *was_detached,
                            int *was_claimed)
{
    int active = libusb_kernel_driver_active(h, iface);

    if (active == 1) {
        if (libusb_detach_kernel_driver(h, iface) != 0)
            return -1;
        *was_detached = 1;
    } else if (active < 0 && active != LIBUSB_ERROR_NOT_SUPPORTED) {
        return -1;
    }

    if (libusb_claim_interface(h, iface) != 0)
        return -1;

    *was_claimed = 1;
    return 0;
}

static int cdc_activate(libusb_device_handle *h)
{
    uint8_t coding[7] = {
        0x00,0xC2,0x01,0x00,
        0x00,
        0x00,
        0x08
    };

    int r = libusb_control_transfer(h, 0x21, 0x20, 0, IFACE_COMM,
                                    coding, sizeof(coding), 1000);

    if (r != (int)sizeof(coding))
        return -1;

    r = libusb_control_transfer(h, 0x21, 0x22, 0x0003, IFACE_COMM,
                                NULL, 0, 1000);

    if (r != 0)
        return -1;

    return 0;
}

static void usb_guard_close(struct usb_guard *g)
{
    if (!g)
        return;

    if (g->h) {
        if (g->claimed_data)
            libusb_release_interface(g->h, IFACE_DATA);
        if (g->claimed_comm)
            libusb_release_interface(g->h, IFACE_COMM);

        if (g->detached_data)
            (void)libusb_attach_kernel_driver(g->h, IFACE_DATA);
        if (g->detached_comm)
            (void)libusb_attach_kernel_driver(g->h, IFACE_COMM);

        libusb_close(g->h);
        g->h = NULL;
    }

    if (g->ctx) {
        libusb_exit(g->ctx);
        g->ctx = NULL;
    }
}

static int open_exact_target(struct usb_guard *g)
{
    libusb_device **list = NULL;
    ssize_t count;
    int matches = 0;
    libusb_device *target = NULL;

    if (libusb_init(&g->ctx) != 0)
        return -1;

    count = libusb_get_device_list(g->ctx, &list);
    if (count < 0)
        return -1;

    for (ssize_t i = 0; i < count; ++i) {
        struct libusb_device_descriptor dd;

        if (libusb_get_device_descriptor(list[i], &dd) != 0)
            continue;

        if (dd.idVendor == VID && dd.idProduct == PID) {
            ++matches;
            target = list[i];
        }
    }

    if (matches != 1 || !target) {
        libusb_free_device_list(list, 1);
        return -2;
    }

    if (libusb_open(target, &g->h) != 0) {
        libusb_free_device_list(list, 1);
        return -3;
    }

    libusb_free_device_list(list, 1);

    if (detach_and_claim(g->h, IFACE_COMM,
                         &g->detached_comm, &g->claimed_comm) != 0)
        return -4;

    if (detach_and_claim(g->h, IFACE_DATA,
                         &g->detached_data, &g->claimed_data) != 0)
        return -5;

    if (cdc_activate(g->h) != 0)
        return -6;

    return 0;
}

/* ----- Qualified WB mapping ----- */

static void psk_kdf(uint8_t out[48])
{
    static const uint8_t salt[29] = {
        'k','g','o','o','d','w','i','x','g',0x00,
        'k','a','e','l','r','g','n','o','e','r','l','i','t','h','m',
        0x00,0x00,0x01,0x80
    };
    uint8_t msg[4 + sizeof(salt)];
    uint8_t mac[32];
    unsigned int mlen = 0;

    for (int i = 1; i <= 2; i++) {
        msg[0] = 0;
        msg[1] = 0;
        msg[2] = 0;
        msg[3] = (uint8_t)i;

        memcpy(msg + 4, salt, sizeof(salt));

        HMAC(EVP_sha256(), WB_KDF_KEY, sizeof(WB_KDF_KEY),
             msg, sizeof(msg), mac, &mlen);

        memcpy(out + (i - 1) * 32, mac, (i == 1) ? 32u : 16u);
    }

    OPENSSL_cleanse(msg, sizeof(msg));
    OPENSSL_cleanse(mac, sizeof(mac));
}

static int psk_derive_v42(const uint8_t *plain,
                          uint32_t len,
                          uint8_t out[32])
{
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    uint8_t hdr[6] = {
        0x02,0xFF,
        (uint8_t)len,
        (uint8_t)(len >> 8),
        (uint8_t)(len >> 16),
        (uint8_t)(len >> 24)
    };
    uint8_t d3[4] = {3,0,0,0};
    uint32_t head = len >> 2;
    unsigned int olen = 0;
    int ok;

    if (!ctx)
        return -1;

    ok = EVP_DigestInit_ex(ctx, EVP_sha256(), NULL) == 1 &&
         EVP_DigestUpdate(ctx, hdr, sizeof(hdr)) == 1 &&
         (head == 0 || EVP_DigestUpdate(ctx, plain, head) == 1);

    for (int i = 0; ok && i < 16; ++i)
        ok = EVP_DigestUpdate(ctx, d3, sizeof(d3)) == 1;

    if (ok)
        ok = EVP_DigestFinal_ex(ctx, out, &olen) == 1 && olen == 32;

    EVP_MD_CTX_free(ctx);
    return ok ? 0 : -1;
}

static int aes_256_gcm_encrypt(const uint8_t key[32],
                               const uint8_t iv[16],
                               const uint8_t *plain,
                               uint32_t len,
                               uint8_t *ct,
                               uint8_t tag[16])
{
    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    int n = 0, n2 = 0;
    int ok;

    if (!ctx)
        return -1;

    ok = EVP_EncryptInit_ex(ctx, EVP_aes_256_gcm(), NULL, NULL, NULL) == 1 &&
         EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, 16, NULL) == 1 &&
         EVP_EncryptInit_ex(ctx, NULL, NULL, key, iv) == 1 &&
         EVP_EncryptUpdate(ctx, NULL, &n, WB_GCM_AAD,
                           (int)sizeof(WB_GCM_AAD)) == 1 &&
         EVP_EncryptUpdate(ctx, ct, &n, plain, (int)len) == 1 &&
         EVP_EncryptFinal_ex(ctx, ct + n, &n2) == 1 &&
         EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, 16, tag) == 1;

    EVP_CIPHER_CTX_free(ctx);
    return ok ? 0 : -1;
}

static int gx_wb_encrypt_qualified(const uint8_t *plain,
                                   uint32_t len,
                                   uint8_t out[WB_LEN])
{
    uint8_t k48[48];
    uint8_t v42[32];
    uint8_t h[32];
    uint8_t msg[6 + 4096 + 16];
    unsigned int hlen = 0;
    size_t n = 0;
    int rc = -1;

    if (len != 32)
        goto out;

    psk_kdf(k48);

    if (psk_derive_v42(plain, len, v42) != 0)
        goto out;

    memset(out, 0, WB_LEN);

    out[32] = 0x02;
    out[33] = 0xFF;
    put_le32(out + 34, len);
    memcpy(out + 38, v42, 16);

    if (aes_256_gcm_encrypt(k48, v42, plain, len,
                            out + 54, out + 54 + len) != 0)
        goto out;

    memcpy(msg + n, out + 32, 6);
    n += 6;

    memcpy(msg + n, out + 54, len + 16);
    n += len + 16;

    HMAC(EVP_sha256(), k48 + 16, 32, msg, n, h, &hlen);

    if (hlen != 32)
        goto out;

    memcpy(out, h, 32);
    rc = 0;

out:
    OPENSSL_cleanse(k48, sizeof(k48));
    OPENSSL_cleanse(v42, sizeof(v42));
    OPENSSL_cleanse(h, sizeof(h));
    OPENSSL_cleanse(msg, sizeof(msg));

    return rc;
}

static int selftest_wb_algorithm(void)
{
    uint8_t psk[32];
    uint8_t wb[WB_LEN];
    uint8_t digest[32];
    int ok = 0;

    for (uint8_t i = 0; i < 32; ++i)
        psk[i] = i;

    if (gx_wb_encrypt_qualified(psk, sizeof(psk), wb) != 0)
        goto out;

    if (sha256_buf(wb, sizeof(wb), digest) != 0)
        goto out;

    ok = CRYPTO_memcmp(digest, WB_TEST_VECTOR_SHA256, 32) == 0;

out:
    OPENSSL_cleanse(psk, sizeof(psk));
    OPENSSL_cleanse(wb, sizeof(wb));
    OPENSSL_cleanse(digest, sizeof(digest));

    return ok ? 0 : -1;
}

/* ----- E0 construction and validation ----- */

static int build_e0_body(const uint8_t bb2[BB2_LEN],
                         const uint8_t wb[WB_LEN],
                         uint8_t body[E0_BODY_LEN])
{
    size_t o = 0;

    put_le32(body + o, DT_BB010002);
    o += 4;
    put_le32(body + o, BB2_LEN);
    o += 4;
    memcpy(body + o, bb2, BB2_LEN);
    o += BB2_LEN;

    put_le32(body + o, DT_BB010003);
    o += 4;
    put_le32(body + o, WB_LEN);
    o += 4;
    memcpy(body + o, wb, WB_LEN);
    o += WB_LEN;

    while (o & 3u)
        body[o++] = 0;

    return o == E0_BODY_LEN ? 0 : -1;
}

static int build_e0_frame(const uint8_t body[E0_BODY_LEN],
                          uint8_t frame[E0_FRAME_LEN])
{
    const uint16_t inner_len = E0_BODY_LEN + 1u;
    const uint16_t payload_len = E0_BODY_LEN + 4u;

    frame[0] = 0xA0;
    frame[1] = (uint8_t)payload_len;
    frame[2] = (uint8_t)(payload_len >> 8);
    frame[3] = (uint8_t)(frame[0] + frame[1] + frame[2]);
    frame[4] = CTRL_E0;
    frame[5] = (uint8_t)inner_len;
    frame[6] = (uint8_t)(inner_len >> 8);

    memcpy(frame + 7, body, E0_BODY_LEN);

    frame[E0_FRAME_LEN - 1u] =
        a0_checksum(CTRL_E0, body, E0_BODY_LEN);

    return 0;
}

static int validate_e0_frame(const uint8_t frame[E0_FRAME_LEN],
                             const uint8_t bb2[BB2_LEN],
                             const uint8_t wb[WB_LEN])
{
    const uint8_t *body = frame + 7;
    size_t o = 0;
    unsigned int sum = 0;

    if (frame[0] != 0xA0 ||
        frame[1] != 0xC8 ||
        frame[2] != 0x01 ||
        frame[3] != 0x69 ||
        frame[4] != CTRL_E0 ||
        frame[5] != 0xC5 ||
        frame[6] != 0x01)
        return -1;

    if (get_le32(body + o) != DT_BB010002)
        return -1;
    o += 4;

    if (get_le32(body + o) != BB2_LEN)
        return -1;
    o += 4;

    if (CRYPTO_memcmp(body + o, bb2, BB2_LEN) != 0)
        return -1;
    o += BB2_LEN;

    if (get_le32(body + o) != DT_BB010003)
        return -1;
    o += 4;

    if (get_le32(body + o) != WB_LEN)
        return -1;
    o += 4;

    if (CRYPTO_memcmp(body + o, wb, WB_LEN) != 0)
        return -1;
    o += WB_LEN;

    if (o + 2u != E0_BODY_LEN ||
        body[o] != 0 ||
        body[o + 1u] != 0)
        return -1;

    for (size_t i = 4; i < E0_FRAME_LEN; ++i)
        sum += frame[i];

    if ((uint8_t)sum != 0xAAu)
        return -1;

    return 0;
}

static int wait_e0_result(libusb_device_handle *h,
                          struct goodix_e0_response *response)
{
    int64_t now = monotonic_ms();
    int64_t deadline;

    if (now < 0)
        return -1;

    deadline = now + 8000;
    goodix_e0_response_init(response);

    while ((now = monotonic_ms()) >= 0 && now < deadline) {
        uint8_t block[USB_CHUNK];
        int remaining = (int)(deadline - now);
        int transferred = 0;
        int result;
        int r;

        if (remaining > 100)
            remaining = 100;
        if (remaining < 1)
            remaining = 1;

        r = libusb_bulk_transfer(h, EP_IN, block, sizeof(block),
                                 &transferred, remaining);

        if (r == LIBUSB_ERROR_TIMEOUT)
            continue;

        if (r != 0) {
            (void)goodix_e0_response_io_error(response);
            return -1;
        }

        if (transferred <= 0)
            continue;

        result = goodix_e0_response_feed(response, block,
                                         (size_t)transferred);
        if (result == GOODIX_E0_FEED_ACCEPTED)
            return 0;
        if (result == GOODIX_E0_FEED_REJECTED)
            return -1;
    }

    (void)goodix_e0_response_timeout(response);
    return -1;
}

/* ----- Minimal TLS 1.2 PSK proof ----- */

static unsigned int tls_psk_cb(SSL *ssl,
                               const char *identity,
                               unsigned char *psk,
                               unsigned int max_psk_len)
{
    struct tls_secret *secret = SSL_get_app_data(ssl);

    if (!secret ||
        secret->used ||
        !identity ||
        strcmp(identity, TLS_IDENTITY) != 0 ||
        max_psk_len < sizeof(secret->psk))
        return 0;

    memcpy(psk, secret->psk, sizeof(secret->psk));
    secret->used = 1;

    return sizeof(secret->psk);
}

static int send_b0_record(libusb_device_handle *h,
                          const uint8_t *record,
                          size_t len)
{
    uint8_t *frame;
    size_t total;
    int rc;

    if (!record || len == 0 || len > 65535u)
        return -1;

    total = 4u + len;
    frame = calloc(1, total);

    if (!frame)
        return -1;

    frame[0] = 0xB0;
    frame[1] = (uint8_t)len;
    frame[2] = (uint8_t)(len >> 8);
    frame[3] = (uint8_t)(frame[0] + frame[1] + frame[2]);
    memcpy(frame + 4, record, len);

    rc = send_padded_frame(h, frame, total);

    OPENSSL_cleanse(frame, total);
    free(frame);

    return rc;
}

static int drain_tls_output(libusb_device_handle *h, SSL *ssl)
{
    BIO *wbio = SSL_get_wbio(ssl);

    while (BIO_ctrl_pending(wbio) > 0) {
        uint8_t hdr[5];
        uint8_t *record = NULL;
        size_t record_len;
        int n;

        if (BIO_ctrl_pending(wbio) < 5)
            return -1;

        n = BIO_read(wbio, hdr, sizeof(hdr));
        if (n != 5)
            return -1;

        record_len = 5u + ((size_t)hdr[3] << 8) + hdr[4];

        if (record_len < 5u || record_len > 65540u)
            return -1;

        record = calloc(1, record_len);
        if (!record)
            return -1;

        memcpy(record, hdr, 5);

        {
            size_t off = 5;
            while (off < record_len) {
                n = BIO_read(wbio, record + off, (int)(record_len - off));
                if (n <= 0) {
                    OPENSSL_cleanse(record, record_len);
                    free(record);
                    return -1;
                }
                off += (size_t)n;
            }
        }

        if (send_b0_record(h, record, record_len) != 0) {
            OPENSSL_cleanse(record, record_len);
            free(record);
            return -1;
        }

        OPENSSL_cleanse(record, record_len);
        free(record);

        /* Match the OEM and qualified reference inter-record pacing. */
        if (sleep_10ms() != 0)
            return -1;
    }

    return 0;
}

static int send_d1(libusb_device_handle *h)
{
    uint8_t body[2] = {0,0};
    uint8_t frame[10] = {0};
    uint16_t inner_len = 3;
    uint16_t payload_len = 6;

    frame[0] = 0xA0;
    frame[1] = (uint8_t)payload_len;
    frame[2] = (uint8_t)(payload_len >> 8);
    frame[3] = (uint8_t)(frame[0] + frame[1] + frame[2]);
    frame[4] = CTRL_D1;
    frame[5] = (uint8_t)inner_len;
    frame[6] = (uint8_t)(inner_len >> 8);
    frame[7] = 0;
    frame[8] = 0;

    /* Qualified project D1 checksum coordinate is D0, not wire D1. */
    frame[9] = a0_checksum_with_coordinate(0xD0, body, sizeof(body));

    return send_padded_frame(h, frame, sizeof(frame));
}

static int tls_handshake_proof(libusb_device_handle *h,
                               const uint8_t psk[32],
                               char *protocol,
                               size_t protocol_cap,
                               char *cipher,
                               size_t cipher_cap)
{
    SSL_CTX *ctx = NULL;
    SSL *ssl = NULL;
    BIO *rbio = NULL, *wbio = NULL;
    struct tls_secret secret;
    int rc = -1;
    int64_t deadline;

    memset(&secret, 0, sizeof(secret));
    memcpy(secret.psk, psk, sizeof(secret.psk));

    ctx = SSL_CTX_new(TLS_server_method());
    if (!ctx)
        goto out;

    if (SSL_CTX_set_min_proto_version(ctx, TLS1_2_VERSION) != 1 ||
        SSL_CTX_set_max_proto_version(ctx, TLS1_2_VERSION) != 1 ||
        SSL_CTX_set_cipher_list(ctx, "PSK-AES128-GCM-SHA256") != 1)
        goto out;

    SSL_CTX_set_options(ctx, SSL_OP_NO_TICKET);
    SSL_CTX_set_psk_server_callback(ctx, tls_psk_cb);

    ssl = SSL_new(ctx);
    rbio = BIO_new(BIO_s_mem());
    wbio = BIO_new(BIO_s_mem());

    if (!ssl || !rbio || !wbio)
        goto out;

    BIO_set_mem_eof_return(rbio, -1);
    SSL_set_bio(ssl, rbio, wbio);
    rbio = NULL;
    wbio = NULL;

    SSL_set_app_data(ssl, &secret);
    SSL_set_accept_state(ssl);

    if (send_d1(h) != 0)
        goto out;

    deadline = monotonic_ms() + 12000;

    while (monotonic_ms() < deadline) {
        uint8_t frame[MAX_FRAME];
        size_t n = 0;
        int hs;

        if (read_one_frame(h, frame, sizeof(frame), 1000, &n) != 0)
            continue;

        if ((frame[0] & 0xF0u) != 0xB0u)
            goto out;

        if (validate_b0_frame(frame, n) != 0)
            goto out;

        if (BIO_write(SSL_get_rbio(ssl),
                      frame + 4,
                      (int)(n - 4u)) != (int)(n - 4u))
            goto out;

        hs = SSL_do_handshake(ssl);

        if (drain_tls_output(h, ssl) != 0)
            goto out;

        if (hs == 1) {
            const char *p = SSL_get_version(ssl);
            const char *c = SSL_get_cipher_name(ssl);

            if (!secret.used || !p || !c)
                goto out;

            snprintf(protocol, protocol_cap, "%s", p);
            snprintf(cipher, cipher_cap, "%s", c);

            rc = 0;
            goto out;
        }

        {
            int e = SSL_get_error(ssl, hs);
            if (e != SSL_ERROR_WANT_READ &&
                e != SSL_ERROR_WANT_WRITE)
                goto out;
        }
    }

out:
    BIO_free(rbio);
    BIO_free(wbio);
    SSL_free(ssl);
    SSL_CTX_free(ctx);
    OPENSSL_cleanse(&secret, sizeof(secret));

    return rc;
}

static int parse_mode(int argc, char **argv, int *commit)
{
    *commit = 0;

    if (argc == 1)
        return 0;

    if (argc == 4 &&
        strcmp(argv[1], "--commit") == 0 &&
        strcmp(argv[2], "--confirm") == 0 &&
        strcmp(argv[3], CONFIRM_PHRASE) == 0) {
        *commit = 1;
        return 0;
    }

    return -1;
}

int main(int argc, char **argv)
{
    struct usb_guard g = {0};
    struct rlimit rl = {0,0};
    struct goodix_e0_response e0_response;
    struct goodix_e0_write_guard write_guard;

    uint8_t bb2[512];
    uint8_t bb2_hash[32];
    uint8_t current_hash[64];

    uint8_t psk[32];
    uint8_t wb[WB_LEN];
    uint8_t wb_hash[32];
    uint8_t e0_body[E0_BODY_LEN];
    uint8_t e0_frame[E0_FRAME_LEN];

    uint8_t rb_bb2[512];
    uint8_t rb_hash[64];

    size_t bb2_len = 0, current_hash_len = 0;
    size_t rb_bb2_len = 0, rb_hash_len = 0;

    char tls_protocol[32] = {0};
    char tls_cipher[64] = {0};

    int commit = 0;
    int post_write = 0;
    int rc = 1;
    enum stage_status transfer_status = STAGE_NOT_ATTEMPTED;
    enum stage_status protocol_status = STAGE_NOT_ATTEMPTED;
    enum stage_status readback_status = STAGE_NOT_ATTEMPTED;
    enum stage_status hash_status = STAGE_NOT_ATTEMPTED;
    enum stage_status tls_status = STAGE_NOT_ATTEMPTED;
    const char *terminal_result = "PREFLIGHT_FAILED";

    memset(bb2, 0, sizeof(bb2));
    memset(bb2_hash, 0, sizeof(bb2_hash));
    memset(current_hash, 0, sizeof(current_hash));

    memset(psk, 0, sizeof(psk));
    memset(wb, 0, sizeof(wb));
    memset(wb_hash, 0, sizeof(wb_hash));
    memset(e0_body, 0, sizeof(e0_body));
    memset(e0_frame, 0, sizeof(e0_frame));

    memset(rb_bb2, 0, sizeof(rb_bb2));
    memset(rb_hash, 0, sizeof(rb_hash));
    goodix_e0_response_init(&e0_response);
    goodix_e0_write_guard_init(&write_guard);

    (void)setrlimit(RLIMIT_CORE, &rl);

    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    signal(SIGHUP, signal_handler);

    if (parse_mode(argc, argv, &commit) != 0) {
        fprintf(stderr,
                "USAGE=%s [--commit --confirm %s]\n",
                argv[0], CONFIRM_PHRASE);
        return 2;
    }

    printf("MODE=%s\n", commit ? "COMMIT_ARMED" : "PREFLIGHT_ONLY");
    printf("TARGET=27c6:5125\n");
    printf("FIRMWARE_REQUIRED=GF_ST411SEC_APP_12509\n");
    printf("LOGICAL_E0_LIMIT=1\n");
    printf("E0_RETRY=FORBIDDEN\n");
    printf("PSK_PRINTED=NO\n");
    printf("PSK_PERSISTED=NO\n");

    if (selftest_wb_algorithm() != 0) {
        printf("WB_ALGORITHM_SELFTEST=FAIL\n");
        goto out;
    }
    printf("WB_ALGORITHM_SELFTEST=PASS\n");

    if (open_exact_target(&g) != 0) {
        printf("USB_TARGET_OPEN=FAIL\n");
        goto out;
    }
    printf("USB_TARGET_OPEN=PASS\n");
    printf("CDC_ACTIVATION=PASS\n");

    if (read_firmware(g.h) != 0) {
        printf("FIRMWARE_GATE=FAIL\n");
        goto out;
    }
    printf("FIRMWARE_GATE=PASS\n");

    if (e4_read(g.h, DT_BB010002,
                bb2, sizeof(bb2), &bb2_len) != 0) {
        printf("PREWRITE_BB010002_READ=FAIL\n");
        goto out;
    }

    if (bb2_len != BB2_LEN ||
        sha256_buf(bb2, bb2_len, bb2_hash) != 0 ||
        CRYPTO_memcmp(bb2_hash, BB010002_E_SHA256, 32) != 0) {
        printf("PREWRITE_BB010002_E=FAIL\n");
        goto out;
    }
    printf("PREWRITE_BB010002_E=PASS\n");

    if (e4_read(g.h, DT_BB020003,
                current_hash, sizeof(current_hash),
                &current_hash_len) != 0) {
        printf("PREWRITE_BB020003_READ=FAIL\n");
        goto out;
    }

    if (current_hash_len != 32u ||
        CRYPTO_memcmp(current_hash, EXPECTED_BB020003_E, 32) != 0) {
        printf("PREWRITE_BB020003_E=FAIL\n");
        goto out;
    }
    printf("PREWRITE_BB020003_E=PASS\n");

    printf("PAIRING_E_BASELINE=PASS\n");

    if (!commit) {
        printf("PREFLIGHT=PASS\n");
        terminal_result = "PREFLIGHT_PASS";
        rc = 0;
        goto out;
    }

    if (RAND_bytes(psk, sizeof(psk)) != 1) {
        printf("PSK_GENERATION=FAIL\n");
        goto out;
    }

    if (mlock(psk, sizeof(psk)) != 0) {
        printf("PSK_MLOCK=FAIL\n");
        goto out;
    }

    printf("PSK_GENERATION=PASS\n");
    printf("PSK_MLOCK=PASS\n");

    if (gx_wb_encrypt_qualified(psk, sizeof(psk), wb) != 0) {
        printf("BB010003_L_BUILD=FAIL\n");
        goto out;
    }
    printf("BB010003_L_BUILD=PASS\n");

    if (sha256_buf(wb, sizeof(wb), wb_hash) != 0) {
        printf("BB020003_L_EXPECTED=FAIL\n");
        goto out;
    }

    if (build_e0_body(bb2, wb, e0_body) != 0 ||
        build_e0_frame(e0_body, e0_frame) != 0 ||
        validate_e0_frame(e0_frame, bb2, wb) != 0) {
        printf("E0_LOCAL_VALIDATION=FAIL\n");
        goto out;
    }

    printf("E0_LOCAL_VALIDATION=PASS\n");
    printf("E0_FRAME_LENGTH=460\n");
    printf("E0_HEADER=A0C80169E0C501\n");

    /*
     * Critical section: exactly one logical E0 attempt. Signals are deferred
     * by the handler until the bounded post-write verification completes.
     */
    write_critical = 1;

    if (goodix_e0_write_guard_begin(&write_guard) != 0) {
        printf("E0_SINGLE_WRITE_GUARD=FAIL\n");
        goto out;
    }

    post_write = 1;
    transfer_status = STAGE_FAIL;

    if (send_padded_frame(g.h, e0_frame, sizeof(e0_frame)) != 0) {
        printf("E0_WRITE_TRANSFER=FAIL\n");
        goto out;
    }

    transfer_status = STAGE_PASS;
    printf("E0_WRITE_TRANSFER=PASS\n");

    protocol_status = STAGE_FAIL;
    if (wait_e0_result(g.h, &e0_response) != 0) {
        printf("E0_OEM_RESPONSE=FAIL\n");
        printf("E0_RESPONSE_ERROR=%s\n",
               goodix_e0_error_name(e0_response.error));
        goto out;
    }
    protocol_status = STAGE_PASS;
    printf("E0_OEM_RESPONSE=PASS\n");
    printf("E0_RESPONSE_CONTROL=0x%02X\n", e0_response.result_control);
    printf("E0_RESPONSE_CODE=0x%02X\n", e0_response.result_code);
    printf("E0_ACK_STATUS=0x%02X\n", e0_response.ack_status);

    readback_status = STAGE_FAIL;
    if (e4_read(g.h, DT_BB010002,
                rb_bb2, sizeof(rb_bb2), &rb_bb2_len) != 0) {
        printf("POSTWRITE_BB010002_READ=FAIL\n");
        goto out;
    }

    if (rb_bb2_len != BB2_LEN ||
        CRYPTO_memcmp(rb_bb2, bb2, BB2_LEN) != 0) {
        printf("POSTWRITE_BB010002_UNCHANGED=FAIL\n");
        goto out;
    }
    readback_status = STAGE_PASS;
    printf("POSTWRITE_BB010002_UNCHANGED=PASS\n");

    hash_status = STAGE_FAIL;
    if (e4_read(g.h, DT_BB020003,
                rb_hash, sizeof(rb_hash), &rb_hash_len) != 0) {
        printf("POSTWRITE_BB020003_READ=FAIL\n");
        goto out;
    }

    if (rb_hash_len != 32u ||
        CRYPTO_memcmp(rb_hash, wb_hash, 32) != 0) {
        printf("POSTWRITE_BB020003_MATCH=FAIL\n");
        goto out;
    }
    hash_status = STAGE_PASS;
    printf("POSTWRITE_BB020003_MATCH=PASS\n");

    tls_status = STAGE_FAIL;
    if (tls_handshake_proof(g.h, psk,
                            tls_protocol, sizeof(tls_protocol),
                            tls_cipher, sizeof(tls_cipher)) != 0) {
        printf("TLS_L_PROOF=FAIL\n");
        goto out;
    }

    tls_status = STAGE_PASS;
    printf("TLS_L_PROOF=PASS\n");
    printf("TLS_PROTOCOL=%s\n", tls_protocol);
    printf("TLS_CIPHER=%s\n", tls_cipher);

    printf("PAIRING_L_PROVISIONED=PASS\n");
    printf("PSK_PRINTED=NO\n");
    printf("PSK_PERSISTED=NO\n");

    terminal_result = "WRITE_VERIFIED";
    rc = 0;

out:
    write_critical = 0;

    if (rc != 0 && post_write) {
        if (transfer_status == STAGE_FAIL)
            terminal_result = "TRANSFER_FAILED_PERSISTENCE_UNKNOWN";
        else
            terminal_result = "WRITE_UNVERIFIED_DO_NOT_RETRY";
    }

    printf("TRANSFER=%s\n", stage_status_name(transfer_status));
    printf("PROTOCOL_RESPONSE=%s\n", stage_status_name(protocol_status));
    printf("READBACK=%s\n", stage_status_name(readback_status));
    printf("HASH_VERIFY=%s\n", stage_status_name(hash_status));
    printf("TLS_VERIFY=%s\n", stage_status_name(tls_status));
    printf("TERMINAL_RESULT=%s\n", terminal_result);
    printf("E0_LOGICAL_WRITE_COUNT=%u\n", write_guard.logical_attempts);

    if (post_write && rc != 0) {
        printf("POST_WRITE_FAILURE=YES\n");
        printf("DO_NOT_RETRY_WRITER=YES\n");
        printf("RECOVER_WITH_WINDOWS_A=YES\n");
    } else {
        printf("POST_WRITE_FAILURE=NO\n");
    }

    if (!post_write)
        printf("WRITE_ATTEMPTED=NO\n");
    else
        printf("WRITE_ATTEMPTED=YES\n");

    usb_guard_close(&g);

    OPENSSL_cleanse(bb2, sizeof(bb2));
    OPENSSL_cleanse(bb2_hash, sizeof(bb2_hash));
    OPENSSL_cleanse(current_hash, sizeof(current_hash));

    OPENSSL_cleanse(psk, sizeof(psk));
    (void)munlock(psk, sizeof(psk));

    OPENSSL_cleanse(wb, sizeof(wb));
    OPENSSL_cleanse(wb_hash, sizeof(wb_hash));
    OPENSSL_cleanse(e0_body, sizeof(e0_body));
    OPENSSL_cleanse(e0_frame, sizeof(e0_frame));

    OPENSSL_cleanse(rb_bb2, sizeof(rb_bb2));
    OPENSSL_cleanse(rb_hash, sizeof(rb_hash));

    OPENSSL_cleanse(tls_protocol, sizeof(tls_protocol));
    OPENSSL_cleanse(tls_cipher, sizeof(tls_cipher));

    printf("KERNEL_REATTACH_ATTEMPTED=YES\n");
    printf("EXIT_CODE=%d\n", rc);

    return rc;
}
