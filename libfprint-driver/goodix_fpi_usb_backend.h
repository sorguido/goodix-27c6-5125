/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_FPI_USB_BACKEND_H
#define GOODIX_FPI_USB_BACKEND_H
#include <gio/gio.h>
typedef struct _FpDevice FpDevice;
typedef struct _GoodixUsbRouter GoodixUsbRouter;
typedef struct _GoodixFpiUsbBackend GoodixFpiUsbBackend;

typedef enum { GOODIX_USB_TRANSFER_IN, GOODIX_USB_TRANSFER_OUT } GoodixUsbDirection;
typedef enum
{
  GOODIX_USB_RECEIVE_NONE = 0,
  GOODIX_USB_RECEIVE_PROTOCOL_RX,
  GOODIX_USB_RECEIVE_PRE_SESSION_SYNC_RX,
} GoodixUsbReceivePurpose;
/* @bytes is borrowed (transfer-none) during the callback. */
typedef void (*GoodixUsbSubmitSeam) (GoodixFpiUsbBackend *backend,
                                     GoodixUsbDirection direction,
                                     guint64 generation, GBytes *bytes,
                                     gpointer user_data);
typedef void (*GoodixFpiUsbBackendDrainedFunc) (GoodixFpiUsbBackend *backend,
                                                gpointer             user_data);
typedef void (*GoodixFpiUsbBackendOutCompletedFunc) (
  GoodixFpiUsbBackend *backend,
  guint64              submit_generation,
  const GError        *error,
  gpointer             user_data);
typedef void (*GoodixFpiUsbBackendInCompletedFunc) (
  GoodixFpiUsbBackend *backend,
  guint64              submit_generation,
  const GError        *error,
  gpointer             user_data);
typedef void (*GoodixFpiUsbBackendSyncCompletedFunc) (
  GoodixFpiUsbBackend *backend,
  guint64              submit_generation,
  const guint8        *data,
  gsize                length,
  const GError        *error,
  gpointer             user_data);

GoodixFpiUsbBackend *goodix_fpi_usb_backend_new (FpDevice *device,
                                                  GoodixUsbRouter *router,
                                                  guint8 in_endpoint,
                                                  guint8 out_endpoint,
                                                  gsize receive_size);
void goodix_fpi_usb_backend_free (GoodixFpiUsbBackend *backend);
void goodix_fpi_usb_backend_set_submit_seam (GoodixFpiUsbBackend *backend,
                                              GoodixUsbSubmitSeam seam,
                                              gpointer user_data);
/* Makes both IN and OUT seam submissions production-shaped/asynchronous. */
void goodix_fpi_usb_backend_set_async_submit_seam (GoodixFpiUsbBackend *backend,
                                                    GoodixUsbSubmitSeam seam,
                                                    gpointer user_data);
void goodix_fpi_usb_backend_set_drained_callback (GoodixFpiUsbBackend *backend,
                                                   GoodixFpiUsbBackendDrainedFunc callback,
                                                   gpointer user_data);
void goodix_fpi_usb_backend_set_out_completed_callback (
  GoodixFpiUsbBackend                 *backend,
  GoodixFpiUsbBackendOutCompletedFunc  callback,
  gpointer                             user_data);
void goodix_fpi_usb_backend_set_in_completed_callback (
  GoodixFpiUsbBackend                *backend,
  GoodixFpiUsbBackendInCompletedFunc  callback,
  gpointer                            user_data);
void goodix_fpi_usb_backend_set_sync_completed_callback (
  GoodixFpiUsbBackend                  *backend,
  GoodixFpiUsbBackendSyncCompletedFunc  callback,
  gpointer                              user_data);
gboolean goodix_fpi_usb_backend_begin_generation (GoodixFpiUsbBackend *backend,
                                                   guint64 generation,
                                                   GCancellable *cancellable,
                                                   GError **error);
gboolean goodix_fpi_usb_backend_arm_receive (GoodixFpiUsbBackend *backend,
                                             guint64 generation,
                                             GError **error);
gboolean goodix_fpi_usb_backend_begin_pre_session_sync (
  GoodixFpiUsbBackend *backend,
  guint64              generation,
  GError              **error);
gboolean goodix_fpi_usb_backend_arm_pre_session_sync_receive (
  GoodixFpiUsbBackend *backend,
  guint64              generation,
  guint                timeout_ms,
  GError              **error);
gboolean goodix_fpi_usb_backend_end_pre_session_sync (
  GoodixFpiUsbBackend *backend,
  guint64              generation,
  GError              **error);
gboolean goodix_fpi_usb_backend_submit_out (GoodixFpiUsbBackend *backend,
                                            guint64 generation, GBytes *bytes,
                                            GError **error);
/* Host seam completion uses the generation captured by its submit token. */
void goodix_fpi_usb_backend_complete_receive (GoodixFpiUsbBackend *backend,
                                              guint64 submit_generation,
                                              const guint8 *data, gsize length,
                                              const GError *error);
void goodix_fpi_usb_backend_complete_out (GoodixFpiUsbBackend *backend,
                                          guint64 submit_generation,
                                          const GError *error);
void goodix_fpi_usb_backend_cancel (GoodixFpiUsbBackend *backend);
gboolean goodix_fpi_usb_backend_is_drained (GoodixFpiUsbBackend *backend);
gboolean goodix_fpi_usb_backend_can_free (GoodixFpiUsbBackend *backend);
guint goodix_fpi_usb_backend_get_outstanding (GoodixFpiUsbBackend *backend);
guint goodix_fpi_usb_backend_get_out_outstanding (GoodixFpiUsbBackend *backend);
guint goodix_fpi_usb_backend_get_max_outstanding (GoodixFpiUsbBackend *backend);
guint goodix_fpi_usb_backend_get_max_out_outstanding (GoodixFpiUsbBackend *backend);
guint64 goodix_fpi_usb_backend_get_delivery_count (GoodixFpiUsbBackend *backend);
guint64 goodix_fpi_usb_backend_get_real_submit_count (GoodixFpiUsbBackend *backend);
guint64 goodix_fpi_usb_backend_get_out_submit_count (GoodixFpiUsbBackend *backend);
guint64 goodix_fpi_usb_backend_get_in_completion_count (GoodixFpiUsbBackend *backend);
guint64 goodix_fpi_usb_backend_get_out_completion_count (GoodixFpiUsbBackend *backend);
GoodixUsbReceivePurpose goodix_fpi_usb_backend_get_receive_purpose (
  GoodixFpiUsbBackend *backend);
gboolean goodix_fpi_usb_backend_pre_session_sync_is_active (
  GoodixFpiUsbBackend *backend);
guint goodix_fpi_usb_backend_get_last_in_timeout_ms (
  GoodixFpiUsbBackend *backend);
#endif
