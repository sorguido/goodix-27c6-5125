/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_fpi_usb_backend.h"
#include "goodix_tls_server.h"
#include "goodix_usb_router.h"
#include <openssl/ssl.h>
#include <string.h>

static const guint8 synthetic_psk[] = {
  0x44,0x32,0x37,0x36,0x2d,0x30,0x34,0x2d,
  0x53,0x59,0x4e,0x54,0x48,0x45,0x54,0x49
};

typedef struct { GByteArray *bytes; } Output;
static void collect_output (GBytes *bytes, gpointer user_data)
{
  Output *out = user_data; gsize length; const guint8 *data = g_bytes_get_data (bytes, &length);
  g_byte_array_append (out->bytes, data, (guint) length);
}
static unsigned int client_psk (SSL *ssl, const char *hint, char *identity,
                                unsigned int max_identity_len,
                                unsigned char *psk, unsigned int max_psk_len)
{
  (void) ssl; (void) hint;
  g_assert_cmpuint (max_identity_len, >, strlen ("Client_identity"));
  g_assert_cmpuint (max_psk_len, >=, sizeof synthetic_psk);
  g_strlcpy (identity, "Client_identity", max_identity_len);
  memcpy (psk, synthetic_psk, sizeof synthetic_psk);
  return sizeof synthetic_psk;
}

static void test_tls_handshake (void)
{
  GoodixTlsAudit audit = { 0 }; Output output = { g_byte_array_new () };
  g_autoptr(GError) error = NULL; GoodixTlsServer *server;
  SSL_CTX *ctx; SSL *client; BIO *in; BIO *out; guint iterations = 0;
  server = goodix_tls_server_new (synthetic_psk, sizeof synthetic_psk,
                                  collect_output, &output, &audit, &error);
  g_assert_no_error (error); g_assert_nonnull (server);
  ctx = SSL_CTX_new (TLS_client_method ()); g_assert_nonnull (ctx);
  g_assert_cmpint (SSL_CTX_set_min_proto_version (ctx, TLS1_2_VERSION), ==, 1);
  g_assert_cmpint (SSL_CTX_set_max_proto_version (ctx, TLS1_2_VERSION), ==, 1);
  g_assert_cmpint (SSL_CTX_set_cipher_list (ctx, "PSK-AES128-GCM-SHA256"), ==, 1);
  SSL_CTX_set_psk_client_callback (ctx, client_psk);
  client = SSL_new (ctx); in = BIO_new (BIO_s_mem ()); out = BIO_new (BIO_s_mem ());
  BIO_set_mem_eof_return (in, -1); SSL_set_bio (client, in, out); SSL_set_connect_state (client);
  while ((!SSL_is_init_finished (client) ||
          goodix_tls_server_get_state (server) != GOODIX_TLS_STATE_ESTABLISHED) && iterations++ < 32)
    {
      guint8 buffer[4096]; int count; int result = SSL_do_handshake (client);
      if (result != 1) { int e = SSL_get_error (client, result); g_assert_true (e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE); }
      while ((count = BIO_read (SSL_get_wbio (client), buffer, sizeof buffer)) > 0)
        g_assert_true (goodix_tls_server_push (server, buffer, (gsize) count, &error));
      g_assert_no_error (error);
      if (output.bytes->len != 0)
        { g_assert_cmpint (BIO_write (SSL_get_rbio (client), output.bytes->data,
                                     (int) output.bytes->len), ==, (int) output.bytes->len);
          g_byte_array_set_size (output.bytes, 0); }
    }
  g_assert_true (SSL_is_init_finished (client));
  g_assert_cmpint (goodix_tls_server_get_state (server), ==, GOODIX_TLS_STATE_ESTABLISHED);
  g_assert_cmpuint (audit.secret_handoff_count, ==, 1);
  g_assert_cmpuint (audit.handshake_count, ==, 1);
  goodix_tls_server_cancel (server);
  goodix_tls_server_cancel (server);
  g_assert_cmpuint (audit.terminal_completion_count, ==, 1);
  goodix_tls_server_free (server);
  g_assert_true (audit.secret_zeroized_on_teardown);
  SSL_free (client); SSL_CTX_free (ctx); g_byte_array_unref (output.bytes);
}

static void test_tls_fail_closed (void)
{
  GoodixTlsAudit audit = { 0 }; g_autoptr(GError) error = NULL;
  GoodixTlsServer *server = goodix_tls_server_new (synthetic_psk, sizeof synthetic_psk,
                                                   NULL, NULL, &audit, &error);
  const guint8 corrupt[] = { 0x16,0x03,0x03,0,2,0xff,0xff };
  g_assert_nonnull (server); g_assert_true (goodix_tls_server_push (server, corrupt, sizeof corrupt, &error));
  g_assert_no_error (error); g_assert_false (goodix_tls_server_eof (server, &error));
  g_assert_nonnull (error); g_clear_error (&error);
  g_assert_false (goodix_tls_server_push (server, corrupt, sizeof corrupt, &error));
  g_assert_cmpuint (audit.terminal_completion_count, ==, 1);
  goodix_tls_server_free (server); g_assert_true (audit.secret_zeroized_on_teardown);
}

typedef struct { guint submit_count; guint a0_count; guint b0_count; } BackendAudit;
static void fake_submit (GoodixFpiUsbBackend *backend, gpointer user_data)
{ BackendAudit *audit = user_data; (void) backend; audit->submit_count++; }
static void a0_cb (guint8 type, GBytes *frame, gpointer user_data)
{ BackendAudit *audit = user_data; (void) frame; g_assert_cmpuint (type, ==, 0xa0); audit->a0_count++; }
static void b0_cb (guint8 type, GBytes *frame, gpointer user_data)
{ BackendAudit *audit = user_data; (void) frame; g_assert_cmpuint (type, ==, 0xb0); audit->b0_count++; }
static void test_backend_single_reader (void)
{
  BackendAudit audit = { 0 }; g_autoptr(GError) error = NULL;
  GoodixUsbRouter *router = goodix_usb_router_new (a0_cb, b0_cb, &audit);
  GoodixFpiUsbBackend *backend = goodix_fpi_usb_backend_new (NULL, router, 0x81, 4096);
  const guint8 b0[] = { 0xb0,1,0,0,0x17 }; guint64 generation = goodix_usb_router_begin_generation (router);
  goodix_fpi_usb_backend_set_submit_seam (backend, fake_submit, &audit);
  g_assert_true (goodix_fpi_usb_backend_arm_receive (backend, generation, &error));
  g_assert_false (goodix_fpi_usb_backend_arm_receive (backend, generation, &error)); g_clear_error (&error);
  g_assert_cmpuint (audit.submit_count, ==, 1); g_assert_cmpuint (goodix_fpi_usb_backend_get_max_outstanding (backend), ==, 1);
  goodix_fpi_usb_backend_complete (backend, generation - 1, b0, sizeof b0, NULL);
  g_assert_cmpuint (audit.b0_count, ==, 0); g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (backend), ==, 1);
  goodix_fpi_usb_backend_complete (backend, generation, b0, sizeof b0, NULL);
  g_assert_cmpuint (audit.b0_count, ==, 1); g_assert_cmpuint (goodix_fpi_usb_backend_get_delivery_count (backend), ==, 1);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (backend), ==, 0);
  goodix_fpi_usb_backend_free (backend); goodix_usb_router_free (router);
}

int main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/goodix/d276-04/tls-handshake", test_tls_handshake);
  g_test_add_func ("/goodix/d276-04/tls-fail-closed", test_tls_fail_closed);
  g_test_add_func ("/goodix/d276-04/backend-single-reader", test_backend_single_reader);
  return g_test_run ();
}
