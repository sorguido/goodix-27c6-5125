/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Clean-room implementation from the OpenSSL 3 public API and canonical
 * protocol facts: TLS 1.2, PSK-AES128-GCM-SHA256, Client_identity. */
#include "goodix_tls_server.h"

#include <openssl/crypto.h>
#include <openssl/err.h>
#include <openssl/ssl.h>
#include <string.h>

#define GOODIX_TLS_IDENTITY "Client_identity"

struct _GoodixTlsServer {
  SSL_CTX *context;
  SSL *ssl;
  guint8 *psk;
  gsize psk_length;
  gboolean handed_off;
  GoodixTlsState state;
  GoodixTlsOutputFunc output;
  gpointer user_data;
  GoodixTlsAudit *audit;
};

static GQuark
goodix_tls_error_quark (void)
{
  return g_quark_from_static_string ("goodix-tls-error");
}

static void
set_terminal (GoodixTlsServer *server, GError **error, const gchar *message)
{
  if (server->state != GOODIX_TLS_STATE_TERMINAL)
    {
      server->state = GOODIX_TLS_STATE_TERMINAL;
      if (server->audit != NULL)
        server->audit->terminal_completion_count++;
    }
  if (error != NULL && *error == NULL)
    g_set_error_literal (error, goodix_tls_error_quark (), 1, message);
}

static unsigned int
psk_server_cb (SSL *ssl, const char *identity, unsigned char *psk,
               unsigned int max_psk_len)
{
  GoodixTlsServer *server = SSL_get_app_data (ssl);

  if (server == NULL || server->handed_off || identity == NULL ||
      strcmp (identity, GOODIX_TLS_IDENTITY) != 0 ||
      server->psk_length > max_psk_len)
    return 0;
  memcpy (psk, server->psk, server->psk_length);
  server->handed_off = TRUE;
  if (server->audit != NULL)
    server->audit->secret_handoff_count++;
  return (unsigned int) server->psk_length;
}

static gboolean
drain_output (GoodixTlsServer *server, GError **error)
{
  BIO *output = SSL_get_wbio (server->ssl);
  guint8 buffer[4096];
  int count;

  while (BIO_ctrl_pending (output) != 0)
    {
      count = BIO_read (output, buffer, sizeof buffer);
      if (count <= 0)
        {
          set_terminal (server, error, "TLS Memory-BIO output failed");
          return FALSE;
        }
      if (server->output != NULL)
        {
          g_autoptr(GBytes) bytes = g_bytes_new (buffer, (gsize) count);
          server->output (bytes, server->user_data);
        }
    }
  return TRUE;
}

GoodixTlsServer *
goodix_tls_server_new (const guint8 *psk, gsize psk_length,
                       GoodixTlsOutputFunc output, gpointer user_data,
                       GoodixTlsAudit *audit, GError **error)
{
  GoodixTlsServer *server;
  BIO *input = NULL;
  BIO *output_bio = NULL;

  g_return_val_if_fail (psk != NULL, NULL);
  if (psk_length == 0 || psk_length > G_MAXUINT)
    {
      g_set_error_literal (error, goodix_tls_error_quark (), 2,
                           "invalid synthetic secret length");
      return NULL;
    }
  server = g_new0 (GoodixTlsServer, 1);
  server->audit = audit;
  server->output = output;
  server->user_data = user_data;
  server->state = GOODIX_TLS_STATE_HANDSHAKE;
  server->psk = g_memdup2 (psk, psk_length);
  server->psk_length = psk_length;
  server->context = SSL_CTX_new (TLS_server_method ());
  if (server->context == NULL ||
      SSL_CTX_set_min_proto_version (server->context, TLS1_2_VERSION) != 1 ||
      SSL_CTX_set_max_proto_version (server->context, TLS1_2_VERSION) != 1 ||
      SSL_CTX_set_cipher_list (server->context, "PSK-AES128-GCM-SHA256") != 1)
    goto fail;
  SSL_CTX_set_options (server->context, SSL_OP_NO_TICKET);
  SSL_CTX_set_psk_server_callback (server->context, psk_server_cb);
  server->ssl = SSL_new (server->context);
  input = BIO_new (BIO_s_mem ());
  output_bio = BIO_new (BIO_s_mem ());
  if (server->ssl == NULL || input == NULL || output_bio == NULL)
    goto fail;
  BIO_set_mem_eof_return (input, -1);
  SSL_set_bio (server->ssl, input, output_bio);
  input = output_bio = NULL;
  SSL_set_app_data (server->ssl, server);
  SSL_set_accept_state (server->ssl);
  return server;

fail:
  BIO_free (input);
  BIO_free (output_bio);
  g_set_error_literal (error, goodix_tls_error_quark (), 3,
                       "OpenSSL TLS 1.2 PSK Memory-BIO setup failed");
  goodix_tls_server_free (server);
  return NULL;
}

gboolean
goodix_tls_server_push (GoodixTlsServer *server, const guint8 *data,
                        gsize length, GError **error)
{
  int result;
  int ssl_error;

  g_return_val_if_fail (server != NULL, FALSE);
  if (server->state == GOODIX_TLS_STATE_TERMINAL || data == NULL || length == 0 ||
      length > G_MAXINT || BIO_write (SSL_get_rbio (server->ssl), data,
                                     (int) length) != (int) length)
    {
      set_terminal (server, error, "TLS input rejected by terminal fence");
      return FALSE;
    }
  result = SSL_do_handshake (server->ssl);
  if (!drain_output (server, error))
    return FALSE;
  if (result == 1)
    {
      server->state = GOODIX_TLS_STATE_ESTABLISHED;
      if (server->audit != NULL)
        server->audit->handshake_count++;
      return TRUE;
    }
  ssl_error = SSL_get_error (server->ssl, result);
  if (ssl_error == SSL_ERROR_WANT_READ || ssl_error == SSL_ERROR_WANT_WRITE)
    return TRUE;
  set_terminal (server, error, "TLS handshake failed closed");
  return FALSE;
}

gboolean
goodix_tls_server_eof (GoodixTlsServer *server, GError **error)
{
  g_return_val_if_fail (server != NULL, FALSE);
  set_terminal (server, error, "truncated TLS stream or terminal EOF");
  return FALSE;
}

void
goodix_tls_server_cancel (GoodixTlsServer *server)
{
  if (server != NULL)
    set_terminal (server, NULL, "cancelled");
}

void
goodix_tls_server_free (GoodixTlsServer *server)
{
  if (server == NULL)
    return;
  SSL_free (server->ssl);
  SSL_CTX_free (server->context);
  if (server->psk != NULL)
    {
      OPENSSL_cleanse (server->psk, server->psk_length);
      if (server->audit != NULL)
        server->audit->secret_zeroized_on_teardown = TRUE;
      g_free (server->psk);
    }
  g_free (server);
}

GoodixTlsState
goodix_tls_server_get_state (const GoodixTlsServer *server)
{
  g_return_val_if_fail (server != NULL, GOODIX_TLS_STATE_TERMINAL);
  return server->state;
}
