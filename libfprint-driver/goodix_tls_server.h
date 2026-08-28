/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_TLS_SERVER_H
#define GOODIX_TLS_SERVER_H
#include <glib.h>
G_BEGIN_DECLS
typedef struct _GoodixTlsServer GoodixTlsServer;
/* Callback bytes are borrowed (transfer-none) for the callback duration.
 * Consumers retaining them must call g_bytes_ref(). */
typedef void (*GoodixTlsOutputFunc) (GBytes *bytes, gpointer user_data);
typedef void (*GoodixTlsPlaintextFunc) (GBytes *bytes, gpointer user_data);
typedef enum { GOODIX_TLS_STATE_HANDSHAKE, GOODIX_TLS_STATE_ESTABLISHED, GOODIX_TLS_STATE_TERMINAL } GoodixTlsState;
typedef struct { guint secret_handoff_count, handshake_count, plaintext_delivery_count, terminal_completion_count; gboolean project_secret_zeroized; gboolean second_handoff_rejected; } GoodixTlsAudit;
GoodixTlsServer *goodix_tls_server_new (const guint8 *psk, gsize psk_length,
                                        GoodixTlsOutputFunc output,
                                        GoodixTlsPlaintextFunc plaintext,
                                        gpointer user_data, GoodixTlsAudit *audit,
                                        GError **error);
gboolean goodix_tls_server_push (GoodixTlsServer *server, const guint8 *data, gsize length, GError **error);
gboolean goodix_tls_server_eof (GoodixTlsServer *server, GError **error);
void goodix_tls_server_cancel (GoodixTlsServer *server);
void goodix_tls_server_free (GoodixTlsServer *server);
GoodixTlsState goodix_tls_server_get_state (const GoodixTlsServer *server);
const gchar *goodix_tls_server_get_protocol (const GoodixTlsServer *server);
const gchar *goodix_tls_server_get_cipher (const GoodixTlsServer *server);
/* Instrumentation seam: proves a second project-secret handoff is rejected. */
gboolean goodix_tls_server_test_second_handoff (GoodixTlsServer *server);
G_END_DECLS
#endif
