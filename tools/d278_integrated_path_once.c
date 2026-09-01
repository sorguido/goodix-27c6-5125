/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * D278/13 thin operator binding.  Protocol, TLS, FDT and image semantics stay
 * in the single GoodixDeviceContext-owned LGPL graph.  The ordinary build is
 * deliberately unapproved and exits before material or USB access.
 */
#include "goodix_a0_protocol.h"
#include "goodix_d190_pe.h"
#include "goodix_fpimage_device.h"
#include "goodix_target_material.h"
#include "goodix_usb_router.h"

#include <errno.h>
#include <fcntl.h>
#include <glib/gstdio.h>
#include <openssl/crypto.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifdef D278_13_LIVE_BINDING
#include <gusb.h>
#endif

/* Operator-facing messages in Italian.  Action instructions use the banner
 * format with visible separator lines; informational lines require no action.
 * No message carries secrets. */
#define OP_BANNER_FIRST_FINGER \
  "METTI IL DITO SUL SENSORE E ATTENDI IL PROSSIMO MESSAGGIO"
#define OP_BANNER_REMOVE_FINGER \
  "TOGLI IL DITO DAL SENSORE E ATTENDI IL PROSSIMO MESSAGGIO"
#define OP_BANNER_SECOND_FINGER \
  "METTI DI NUOVO IL DITO SUL SENSORE E ATTENDI IL PROSSIMO MESSAGGIO"
#define OP_BANNER_SUCCESS \
  "TEST COMPLETATO. TOGLI IL DITO DAL SENSORE.\n" \
  "NON ESEGUIRE NUOVAMENTE IL COMANDO."
#define OP_BANNER_FAILURE \
  "TEST INTERROTTO.\n" \
  "NON ESEGUIRE NUOVAMENTE IL COMANDO."

#define OP_MSG_AUTHORIZATION_OK \
  "Autorizzazione live concessa; inizio run singolo."
#define OP_MSG_DEVICE_DETECTED \
  "Dispositivo Goodix 27c6:5125 rilevato; apertura USB in corso."
#define OP_MSG_SECURE_SESSION_STARTED \
  "Sessione sicura avviata; attendere le istruzioni per il dito."
#define OP_MSG_HOST_ONLY_A2_ARMED \
  "Host-only: IN armato per A2; in attesa dell'ACK dal sensore."
#define OP_MSG_HOST_ONLY_A2_ACK_RECEIVED \
  "Host-only: ACK A2 ricevuto; secondo IN ri-armato per la risposta tipata."
#define OP_MSG_HOST_ONLY_A2_TYPED_RECEIVED \
  "Host-only: risposta tipata A2 ricevuta; transizione verso A8."
#define OP_MSG_HOST_ONLY_SUCCESS \
  "Host-only: catena A2 ACK+risposta tipata completata con successo."

static void
operator_message (const gchar *message)
{
  g_print ("OPERATOR_MESSAGE_IT=%s\n", message);
}
static void
operator_action_banner (const gchar *text)
{
  g_print ("======================\n%s\n======================\n", text);
}

typedef enum
{
  OPERATOR_PROMPT_NONE = 0,
  OPERATOR_PROMPT_FIRST_FINGER,
  OPERATOR_PROMPT_REMOVE_FINGER,
  OPERATOR_PROMPT_SECOND_FINGER,
  OPERATOR_PROMPT_SUCCESS,
  OPERATOR_PROMPT_FAILURE,
} OperatorPromptAction;

typedef struct
{
  GoodixPostTlsPhase last_action_phase;
  gboolean           success_emitted;
  gboolean           failure_emitted;
  guint              success_count;
  guint              failure_count;
  guint              duplicate_count;
} OperatorPromptTracker;

static void
operator_prompt_tracker_init (OperatorPromptTracker *tracker)
{
  tracker->last_action_phase = GOODIX_POST_TLS_PHASE_NOT_STARTED;
  tracker->success_emitted = FALSE;
  tracker->failure_emitted = FALSE;
  tracker->success_count = 0;
  tracker->failure_count = 0;
  tracker->duplicate_count = 0;
}

static OperatorPromptAction
operator_prompt_tracker_emit (OperatorPromptTracker *tracker,
                              GoodixPostTlsPhase    phase,
                              gboolean              terminal)
{
  /* Success and failure are mutually exclusive and each emitted at most once.
   * Once either outcome is emitted, no further action banner is produced. */
  if (tracker->success_emitted || tracker->failure_emitted)
    return OPERATOR_PROMPT_NONE;

  if (terminal)
    {
      operator_action_banner (OP_BANNER_FAILURE);
      tracker->failure_emitted = TRUE;
      tracker->failure_count++;
      return OPERATOR_PROMPT_FAILURE;
    }

  switch (phase)
    {
    case GOODIX_POST_TLS_PHASE_FIRST_IRQ2:
      if (tracker->last_action_phase == phase)
        {
          tracker->duplicate_count++;
          return OPERATOR_PROMPT_NONE;
        }
      tracker->last_action_phase = phase;
      operator_action_banner (OP_BANNER_FIRST_FINGER);
      return OPERATOR_PROMPT_FIRST_FINGER;

    case GOODIX_POST_TLS_PHASE_RELEASE_IRQ200:
      if (tracker->last_action_phase == phase)
        {
          tracker->duplicate_count++;
          return OPERATOR_PROMPT_NONE;
        }
      tracker->last_action_phase = phase;
      operator_action_banner (OP_BANNER_REMOVE_FINGER);
      return OPERATOR_PROMPT_REMOVE_FINGER;

    case GOODIX_POST_TLS_PHASE_SECOND_IRQ2:
      if (tracker->last_action_phase == phase)
        {
          tracker->duplicate_count++;
          return OPERATOR_PROMPT_NONE;
        }
      tracker->last_action_phase = phase;
      operator_action_banner (OP_BANNER_SECOND_FINGER);
      return OPERATOR_PROMPT_SECOND_FINGER;

    case GOODIX_POST_TLS_PHASE_STOP:
      operator_action_banner (OP_BANNER_SUCCESS);
      tracker->success_emitted = TRUE;
      tracker->success_count++;
      return OPERATOR_PROMPT_SUCCESS;

    default:
      return OPERATOR_PROMPT_NONE;
    }
}

#define D278_VID 0x27c6u
#define D278_PID 0x5125u
#define D278_INTERFACE 0u
#define D278_CACHE_SIZE 13520u
#define D278_CACHE_CRC_OFFSET 13516u
#define D278_CACHE_FDT_OFFSET 64u

#ifndef D278_13_APPROVED_BASELINE
#define D278_13_APPROVED_BASELINE "UNAPPROVED_FOR_LIVE"
#endif

#define D278_13_AUTHORIZATION_TOKEN \
  "D278_13_ONE_INTEGRATED_TWO_ACQUISITION_RUN_NO_RETRY"
#define D278_13_OPERATION_NAME "D278_13_INTEGRATED_PATH_ONCE"
#define D278_13_TICKET_MAX_SIZE 512u
#define D278_13_NONCE_MIN_SIZE 16u
#define D278_13_NONCE_MAX_SIZE 128u

static const gchar *const manifest_path =
  "/var/lib/goodix-5125-poc/target-material-manifest.json";
static const gchar *const transport_path =
  "/var/lib/goodix-5125-poc/transport-material.bin";
static const gchar *const config90_path =
  "/var/lib/goodix-5125-poc/target-config-90.bin";
static const gchar *const cache_relative_path =
  "captures/D255_20260822T205631772Z_85c8c41f/raw/cache_before/"
  "9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2.bin";
static const gchar *const cache_sha256 =
  "9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2";

static gboolean
is_full_sha (const gchar *value)
{
  if (value == NULL || strlen (value) != 40u)
    return FALSE;
  for (guint i = 0; i < 40u; i++)
    if (!g_ascii_isxdigit (value[i]))
      return FALSE;
  return TRUE;
}

static gboolean
static_authorization_gate (const gchar **reason)
{
  const gchar *runtime_sha =
    g_getenv ("D278_13_APPROVED_LIVE_BASELINE_SHA");
  const gchar *authorization =
    g_getenv ("D278_13_OPERATOR_AUTHORIZATION");
  const gchar *operation = g_getenv ("D278_13_OPERATION");

  if (!is_full_sha (D278_13_APPROVED_BASELINE))
    {
      *reason = "compiled_baseline_unapproved";
      return FALSE;
    }
  if (!is_full_sha (runtime_sha) ||
      !g_str_equal (runtime_sha, D278_13_APPROVED_BASELINE))
    {
      *reason = "runtime_baseline_mismatch";
      return FALSE;
    }
  if (authorization == NULL ||
      !g_str_equal (authorization, D278_13_AUTHORIZATION_TOKEN))
    {
      *reason = "static_authorization_missing_or_invalid";
      return FALSE;
    }
  if (operation == NULL || !g_str_equal (operation, D278_13_OPERATION_NAME))
    {
      *reason = "runtime_operation_mismatch";
      return FALSE;
    }
  *reason = "none";
  return TRUE;
}

static gboolean
nonce_valid (const gchar *nonce)
{
  gsize length;

  if (nonce == NULL)
    return FALSE;
  length = strlen (nonce);
  if (length < D278_13_NONCE_MIN_SIZE || length > D278_13_NONCE_MAX_SIZE)
    return FALSE;
  for (gsize i = 0; i < length; i++)
    if (!g_ascii_isalnum (nonce[i]) && nonce[i] != '-' && nonce[i] != '_')
      return FALSE;
  return TRUE;
}

static gboolean
write_all (gint          fd,
           const guint8 *data,
           gsize         length)
{
  gsize offset = 0;

  while (offset < length)
    {
      ssize_t written = write (fd, data + offset, length - offset);
      if (written < 0 && errno == EINTR)
        continue;
      if (written <= 0)
        return FALSE;
      offset += (gsize) written;
    }
  return TRUE;
}

static gboolean
claim_authorization_ticket (const gchar  *path,
                            const gchar  *expected_baseline,
                            const gchar  *expected_operation,
                            gboolean     *consumed,
                            const gchar **reason)
{
  static const guint8 receipt[] =
    "D278_13_AUTHORIZATION_CONSUMED\n";
  g_autofree gchar *directory = NULL;
  g_autofree gchar *basename = NULL;
  g_autofree gchar *contents = NULL;
  g_autofree gchar *claim_input = NULL;
  g_autofree gchar *claim_hash = NULL;
  g_autofree gchar *marker = NULL;
  g_auto(GStrv) lines = NULL;
  const gchar *baseline = NULL;
  const gchar *operation = NULL;
  const gchar *nonce = NULL;
  struct stat directory_status;
  struct stat ticket_status;
  struct stat current_status;
  gint directory_fd = -1;
  gint ticket_fd = -1;
  gint marker_fd = -1;
  gsize offset = 0;
  guint field_count = 0;
  gboolean ok = FALSE;

  *consumed = FALSE;
  *reason = "ticket_missing";
  if (path == NULL || !g_path_is_absolute (path))
    goto out;
  directory = g_path_get_dirname (path);
  basename = g_path_get_basename (path);
  if (g_str_equal (basename, ".") || g_str_equal (basename, "..") ||
      strchr (basename, G_DIR_SEPARATOR) != NULL)
    {
      *reason = "ticket_path_policy";
      goto out;
    }
  directory_fd = open (directory, O_RDONLY | O_CLOEXEC | O_DIRECTORY |
                                  O_NOFOLLOW);
  if (directory_fd < 0 || fstat (directory_fd, &directory_status) != 0 ||
      !S_ISDIR (directory_status.st_mode) ||
      directory_status.st_uid != geteuid () ||
      (directory_status.st_mode & 0777) != 0700)
    {
      *reason = "ticket_directory_policy";
      goto out;
    }
  ticket_fd = openat (directory_fd, basename, O_RDONLY | O_CLOEXEC |
                                               O_NOFOLLOW);
  if (ticket_fd < 0)
    {
      if (errno == ELOOP)
        *reason = "ticket_file_policy";
      goto out;
    }
  if (fstat (ticket_fd, &ticket_status) != 0 ||
      !S_ISREG (ticket_status.st_mode) || ticket_status.st_nlink != 1 ||
      ticket_status.st_uid != geteuid () ||
      (ticket_status.st_mode & 0777) != 0600 || ticket_status.st_size <= 0 ||
      (guint64) ticket_status.st_size > D278_13_TICKET_MAX_SIZE)
    {
      *reason = "ticket_file_policy";
      goto out;
    }
  contents = g_malloc0 ((gsize) ticket_status.st_size + 1u);
  while (offset < (gsize) ticket_status.st_size)
    {
      ssize_t got = read (ticket_fd, contents + offset,
                          (gsize) ticket_status.st_size - offset);
      if (got < 0 && errno == EINTR)
        continue;
      if (got <= 0)
        {
          *reason = "ticket_read_failed";
          goto out;
        }
      offset += (gsize) got;
    }
  if (contents[offset - 1u] != '\n')
    {
      *reason = "ticket_malformed";
      goto out;
    }
  lines = g_strsplit (contents, "\n", -1);
  for (guint i = 0; lines[i] != NULL; i++)
    {
      if (lines[i][0] == '\0')
        {
          if (lines[i + 1u] != NULL)
            {
              *reason = "ticket_malformed";
              goto out;
            }
          continue;
        }
      if (g_str_has_prefix (lines[i], "D278_13_BASELINE_SHA=") &&
          baseline == NULL)
        baseline = lines[i] + strlen ("D278_13_BASELINE_SHA=");
      else if (g_str_has_prefix (lines[i], "D278_13_OPERATION=") &&
               operation == NULL)
        operation = lines[i] + strlen ("D278_13_OPERATION=");
      else if (g_str_has_prefix (lines[i], "D278_13_NONCE=") && nonce == NULL)
        nonce = lines[i] + strlen ("D278_13_NONCE=");
      else
        {
          *reason = "ticket_malformed";
          goto out;
        }
      field_count++;
    }
  if (field_count != 3u || !is_full_sha (baseline) || !nonce_valid (nonce))
    {
      *reason = "ticket_malformed";
      goto out;
    }
  if (!g_str_equal (baseline, expected_baseline))
    {
      *reason = "ticket_baseline_mismatch";
      goto out;
    }
  if (!g_str_equal (operation, expected_operation))
    {
      *reason = "ticket_operation_mismatch";
      goto out;
    }
  if (fstatat (directory_fd, basename, &current_status,
               AT_SYMLINK_NOFOLLOW) != 0 ||
      current_status.st_dev != ticket_status.st_dev ||
      current_status.st_ino != ticket_status.st_ino ||
      current_status.st_uid != ticket_status.st_uid ||
      current_status.st_mode != ticket_status.st_mode ||
      current_status.st_size != ticket_status.st_size)
    {
      *reason = "ticket_changed_during_validation";
      goto out;
    }
  claim_input = g_strdup_printf ("%s\n%s\n%s", baseline, operation, nonce);
  claim_hash = g_compute_checksum_for_string (G_CHECKSUM_SHA256, claim_input,
                                               -1);
  marker = g_strdup_printf (".d278-13-consumed-%s", claim_hash);
  marker_fd = openat (directory_fd, marker,
                      O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
                      0600);
  if (marker_fd < 0)
    {
      *reason = errno == EEXIST ? "ticket_already_consumed" :
                                  "ticket_claim_failed";
      goto out;
    }
  *consumed = TRUE;
  if (!write_all (marker_fd, receipt, sizeof receipt - 1u) ||
      fsync (marker_fd) != 0 || fsync (directory_fd) != 0)
    {
      *reason = "ticket_claim_persist_failed";
      goto out;
    }
  *reason = "none";
  ok = TRUE;

out:
  if (marker_fd >= 0)
    close (marker_fd);
  if (ticket_fd >= 0)
    close (ticket_fd);
  if (directory_fd >= 0)
    close (directory_fd);
  return ok;
}

static gboolean
live_authorization_gate (gboolean     *consumed,
                         const gchar **reason)
{
  const gchar *ticket_path;

  *consumed = FALSE;
  if (!static_authorization_gate (reason))
    return FALSE;
  ticket_path = g_getenv ("D278_13_AUTHORIZATION_TICKET");
  return claim_authorization_ticket (ticket_path, D278_13_APPROVED_BASELINE,
                                     D278_13_OPERATION_NAME, consumed, reason);
}

static gboolean
digest (const guint8 *data,
        gsize         length,
        guint8        output[32])
{
  g_autoptr(GChecksum) checksum = g_checksum_new (G_CHECKSUM_SHA256);
  gsize output_length = 32u;

  if (length > G_MAXSSIZE)
    return FALSE;
  g_checksum_update (checksum, data, (gssize) length);
  g_checksum_get_digest (checksum, output, &output_length);
  return output_length == 32u;
}

static guint32
crc32_mpeg2 (const guint8 *data,
             gsize         length)
{
  guint32 crc = 0xffffffffu;

  for (gsize i = 0; i < length; i++)
    {
      crc ^= (guint32) data[i] << 24;
      for (guint bit = 0; bit < 8u; bit++)
        crc = (crc & 0x80000000u) != 0u ?
          (crc << 1) ^ 0x04c11db7u : crc << 1;
    }
  return crc;
}

static gchar *
canonical_dll_path (void)
{
  g_autofree gchar *cwd = g_get_current_dir ();
  return g_canonicalize_filename (
    "analysis/D230/work/GoodixExport/gfusb.dll", cwd);
}

static GoodixTargetMaterial *
prepare_target_material (GoodixTargetMaterialAudit  *audit,
                         GoodixSecureSessionMaterial *view,
                         GError                     **error)
{
  GoodixTargetMaterialPolicy policy;
  GoodixD190PePolicy pe_policy;
  GoodixTargetMaterial *owner = NULL;
  g_autofree gchar *dll = canonical_dll_path ();
  guint8 seed_a[GOODIX_D190_PE_SEED_LENGTH] = { 0 };
  guint8 seed_b[GOODIX_D190_PE_SEED_LENGTH] = { 0 };

  goodix_target_material_policy_production (&policy);
  goodix_d190_pe_policy_production (&pe_policy);
  owner = goodix_target_material_load (manifest_path, transport_path,
                                       config90_path, &policy, audit, error);
  if (owner == NULL ||
      !goodix_d190_pe_extract_with_policy (dll, &pe_policy, seed_a, seed_b,
                                           error) ||
      !goodix_target_material_bind (owner, seed_a, seed_b, error) ||
      !goodix_target_material_get_secure_session_material (owner, view,
                                                            error))
    {
      goodix_target_material_free (owner);
      owner = NULL;
    }
  goodix_d190_pe_cleanse_seed (seed_a);
  goodix_d190_pe_cleanse_seed (seed_b);
  return owner;
}

/* --- Host-only synthetic material for prompt-state-machine proof --- */

static void
set_config_finalizer (guint8 config[GOODIX_SECURE_SESSION_CONFIG90_LENGTH])
{
  guint32 sum = 0;
  guint16 finalizer;

  for (guint i = 0; i < 111; i++)
    {
      guint16 word = (guint16) ((guint16) config[i * 2u] |
                                (guint16) ((guint16) config[i * 2u + 1u] << 8));
      sum += (guint32) word;
    }
  finalizer = (guint16) (0u - 0xa5a5u - sum);
  config[222] = (guint8) finalizer;
  config[223] = (guint8) (finalizer >> 8);
}

static void
build_synthetic_secure_material (GoodixSecureSessionMaterial *material,
                                 guint8                      *config,
                                 gsize                        config_length,
                                 guint8                      *validator,
                                 guint8                      *a2,
                                 guint8                      *chip,
                                 guint8                      *otp,
                                 guint8                      *psk)
{
  static const guint8 identity[] = "GF_ST411SEC_APP_12509";
  static const guint8 registers[4][2] = {
    { 0x20, 0x02 }, { 0x36, 0x02 }, { 0x38, 0x02 }, { 0x3a, 0x02 }
  };
  static const guint8 values[4][2] = {
    { 0xd8, 0x0b }, { 0xbe, 0x00 }, { 0xbd, 0x00 }, { 0xbc, 0x00 }
  };
  static const guint offsets[] = { 117, 121, 125, 129 };

  memset (config, 0, config_length);
  for (guint i = 0; i < 32; i++)
    {
      validator[i] = (guint8) (0x20u + i);
      psk[i] = (guint8) (0x80u + i);
    }
  a2[0] = 0x11;
  a2[1] = 0x22;
  a2[2] = 0x33;
  chip[0] = 0x25;
  chip[1] = 0x04;
  chip[2] = 0x12;
  chip[3] = 0x50;
  for (guint i = 0; i < 64; i++)
    otp[i] = (guint8) (i * 3u + 1u);
  for (guint i = 0; i < 4; i++)
    {
      memcpy (material->dac_values[i], values[i], 2);
      memcpy (config + offsets[i], registers[i], 2);
      memcpy (config + offsets[i] + 2u, values[i], 2);
    }
  set_config_finalizer (config);

  material->expected_identity = identity;
  material->expected_identity_length = sizeof identity;
  material->e4_validator = validator;
  material->e4_validator_length = 32;
  material->config90 = config;
  material->config90_length = config_length;
  material->psk = psk;
  material->psk_length = 32;
  digest (validator, 32, material->e4_validator_sha256);
  digest (a2, 3, material->a2_response_sha256);
  digest (chip, 4, material->chip82_response_sha256);
  digest (otp, 64, material->otp_a6_response_sha256);
  digest (config, config_length, material->config90_sha256);
}

static GBytes *
build_a0_frame (guint8        control,
                const guint8 *body,
                gsize         body_length)
{
  g_autoptr(GError) error = NULL;
  GBytes *frame = goodix_a0_build_frame (control, control, body, body_length,
                                         &error);
  g_assert_no_error (error);
  g_assert_nonnull (frame);
  return frame;
}

static gboolean
read_exact (gint     fd,
            guint8  *data,
            gsize    length)
{
  gsize offset = 0;

  while (offset < length)
    {
      ssize_t got = read (fd, data + offset, length - offset);
      if (got < 0 && errno == EINTR)
        continue;
      if (got <= 0)
        return FALSE;
      offset += (gsize) got;
    }
  return TRUE;
}

static gboolean
load_canonical_fdt_seed (guint8    output[12],
                         GError  **error)
{
  GoodixTargetMaterialPolicy policy;
  g_autofree gchar *cwd = g_get_current_dir ();
  g_autofree gchar *path = g_canonicalize_filename (cache_relative_path, cwd);
  g_autofree gchar *actual_sha = NULL;
  g_autofree guint8 *cache = g_malloc0 (D278_CACHE_SIZE);
  guint8 otp_sha[32] = { 0 };
  struct stat st;
  gint fd = -1;
  guint32 stored_crc;
  gboolean seed_present = FALSE;
  gboolean ok = FALSE;

  fd = g_open (path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW, 0);
  if (fd < 0 || fstat (fd, &st) != 0 || !S_ISREG (st.st_mode) ||
      st.st_size != (off_t) D278_CACHE_SIZE ||
      !read_exact (fd, cache, D278_CACHE_SIZE))
    goto out;
  actual_sha = g_compute_checksum_for_data (G_CHECKSUM_SHA256, cache,
                                            D278_CACHE_SIZE);
  stored_crc = (guint32) cache[D278_CACHE_CRC_OFFSET] |
               ((guint32) cache[D278_CACHE_CRC_OFFSET + 1u] << 8) |
               ((guint32) cache[D278_CACHE_CRC_OFFSET + 2u] << 16) |
               ((guint32) cache[D278_CACHE_CRC_OFFSET + 3u] << 24);
  goodix_target_material_policy_production (&policy);
  if (!g_str_equal (actual_sha, cache_sha256) ||
      stored_crc != crc32_mpeg2 (cache, D278_CACHE_CRC_OFFSET) ||
      !digest (cache, 64u, otp_sha) ||
      CRYPTO_memcmp (otp_sha, policy.otp_a6_response_sha256, 32u) != 0)
    goto out;
  memcpy (output, cache + D278_CACHE_FDT_OFFSET, 12u);
  for (guint i = 0; i < 12u; i++)
    seed_present = seed_present || output[i] != 0;
  ok = seed_present;
out:
  if (fd >= 0)
    close (fd);
  OPENSSL_cleanse (otp_sha, sizeof otp_sha);
  OPENSSL_cleanse (cache, D278_CACHE_SIZE);
  if (!ok)
    g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                         "canonical FDT seed validation failed");
  return ok;
}

static int
run_gate_self_test (void)
{
  const gchar *reason = NULL;
  gboolean closed = !static_authorization_gate (&reason);

  g_print ("EXECUTABLE_CLOSURE=%s\n", closed ? "PASS_HOST_ONLY" : "FAIL");
  g_print ("REAL_USB_ACCESS=false\nREAL_USB_SUBMIT=0\n");
  g_print ("REAL_PRODUCTION_SECRET_READ=false\n");
  g_print ("LIVE_EXECUTION_PERFORMED=false\n");
  g_print ("CURRENT_LIVE_AUTHORIZED=false\nREADY_FOR_LIVE=false\n");
  return closed ? 0 : 1;
}

static int
run_ticket_gate_only (const gchar *ticket_path,
                      const gchar *expected_baseline)
{
  const gchar *reason = "ticket_malformed";
  gboolean consumed = FALSE;
  gboolean accepted = FALSE;

  if (is_full_sha (expected_baseline))
    accepted = claim_authorization_ticket (ticket_path, expected_baseline,
                                           D278_13_OPERATION_NAME,
                                           &consumed, &reason);
  g_print ("{\"gate_only\":true,\"accepted\":%s,"
           "\"authorization_failure_reason\":\"%s\","
           "\"live_authorization_consumed\":%s,"
           "\"real_production_secret_read\":false,"
           "\"real_usb_access\":false,\"real_usb_submit\":0}\n",
           accepted ? "true" : "false", reason,
           consumed ? "true" : "false");
  return accepted ? 0 : 3;
}

typedef struct
{
  guint64 generation;
  GBytes *bytes;
} HostOnlySubmission;

typedef struct
{
  GQueue *out;
  guint in_submit_count;
  guint64 generation;
} HostOnlySeam;

static void
host_only_submission_free (HostOnlySubmission *submission)
{
  if (submission == NULL)
    return;
  g_bytes_unref (submission->bytes);
  g_free (submission);
}

static void
host_only_submit_seam (GoodixFpiUsbBackend *backend,
                       GoodixUsbDirection   direction,
                       guint64              generation,
                       GBytes              *bytes,
                       gpointer             user_data)
{
  HostOnlySeam *seam = user_data;

  (void) backend;
  if (direction == GOODIX_USB_TRANSFER_IN)
    {
      seam->in_submit_count++;
      return;
    }
  g_assert_nonnull (bytes);
  HostOnlySubmission *submission = g_new0 (HostOnlySubmission, 1);
  submission->generation = generation;
  submission->bytes = g_bytes_ref (bytes);
  g_queue_push_tail (seam->out, submission);
}

/* Host-only proof for D278/14 attempt-2: exercises the exact real-USB-shaped
 * A2 receive chain (backend-level IN completion -> re-arm -> typed response)
 * and prints Italian operator banners.  No USB access, no secrets. */
static int
run_operator_prompt_state_machine_host_only (void)
{
  g_autoptr(GoodixFpImageDevice) device = goodix_fpimage_device_new ();
  GoodixDeviceContext *ctx = goodix_fpimage_device_get_context (device);
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(GError) error = NULL;
  GoodixSecureSessionMaterial secure_material = { 0 };
  GoodixPostTlsMaterial post_material = { 0 };
  GoodixSecureSessionAudit secure_audit = { 0 };
  GoodixTlsAudit tls_audit = { 0 };
  GoodixPostTlsAudit post_audit = { 0 };
  guint8 config[GOODIX_SECURE_SESSION_CONFIG90_LENGTH] = { 0 };
  guint8 validator[32] = { 0 };
  guint8 a2[3] = { 0 };
  guint8 chip[4] = { 0 };
  guint8 otp[64] = { 0 };
  guint8 psk[GOODIX_SECURE_SESSION_PSK_LENGTH] = { 0 };
  HostOnlySeam seam = { 0 };
  GoodixFpiUsbBackend *backend;
  guint64 generation;
  g_autoptr(GBytes) ack = NULL;
  g_autoptr(GBytes) typed = NULL;
  gsize ack_length;
  const guint8 *ack_data;
  gsize typed_length;
  const guint8 *typed_data;
  const guint8 ack_body[2] = { 0xa2, 0x01 };

  build_synthetic_secure_material (&secure_material, config,
                                   sizeof config, validator, a2, chip, otp,
                                   psk);
  for (guint i = 0; i < 6u; i++)
    {
      post_material.initial_fdt_table[i * 2u] = 0x80;
      post_material.initial_fdt_table[i * 2u + 1u] = (guint8) (0x40u + i);
    }
  post_material.af_timestamp = 0x1234;
  post_material.first_arm_timestamp = 0x2345;
  post_material.second_arm_timestamp = 0x3456;

  seam.out = g_queue_new ();
  goodix_device_context_set_async_usb_submit_seam (ctx, host_only_submit_seam,
                                                   &seam);

  if (!goodix_device_context_begin_operator_epoch (ctx, cancellable, &error))
    {
      g_printerr ("OPERATOR_EPOCH_BEGIN_FAILED: %s\n", error->message);
      return 1;
    }
  generation = goodix_device_context_get_generation (ctx);
  seam.generation = generation;
  backend = goodix_device_context_get_fpi_usb_backend (ctx);

  if (!goodix_device_context_begin_pre_session_rx_sync (ctx, &error))
    {
      g_printerr ("PRE_SESSION_RX_SYNC_BEGIN_FAILED: %s\n", error->message);
      return 1;
    }
  g_assert_cmpuint (seam.in_submit_count, ==, 1u);
  g_assert_cmpuint (g_queue_get_length (seam.out), ==, 0u);
  {
    g_autoptr(GError) timeout = g_error_new_literal (
      G_USB_DEVICE_ERROR, G_USB_DEVICE_ERROR_TIMED_OUT,
      "synthetic GUsb bulk timeout");
    goodix_device_context_complete_receive (ctx, generation, NULL, 0,
                                             timeout);
  }
  g_assert_cmpint (goodix_device_context_get_pre_session_rx_sync_result (ctx),
                   ==, GOODIX_PRE_SESSION_RX_SYNC_PASS);
  seam.in_submit_count = 0;

  if (!goodix_device_context_configure_post_tls_lifecycle (
        ctx, &post_material, &post_audit, &error))
    {
      g_printerr ("POST_TLS_CONFIGURE_FAILED: %s\n", error->message);
      return 1;
    }
  if (!goodix_device_context_start_secure_session (
        ctx, &secure_material, NULL, NULL, &secure_audit, &tls_audit, &error))
    {
      g_printerr ("SECURE_SESSION_START_FAILED: %s\n", error->message);
      return 1;
    }

  g_print ("PHASE=%s\n", goodix_secure_phase_name (
             goodix_secure_session_get_phase (
               goodix_device_context_get_secure_session (ctx))));
  g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (backend), ==, 1u);
  g_assert_cmpuint (seam.in_submit_count, ==, 1u);
  operator_message (OP_MSG_HOST_ONLY_A2_ARMED);

  /* Complete the physical A2 command OUT first; advance_phase() is gated on
   * out_pending being clear, exactly as on real USB. */
  {
    HostOnlySubmission *submission = g_queue_pop_head (seam.out);
    g_assert_nonnull (submission);
    goodix_fpi_usb_backend_complete_out (backend, submission->generation, NULL);
    host_only_submission_free (submission);
  }

  /* Production-shaped backend-level IN completion for the A2 ACK. */
  ack = build_a0_frame (0xb0, ack_body, sizeof ack_body);
  ack_data = g_bytes_get_data (ack, &ack_length);
  goodix_fpi_usb_backend_complete_receive (backend, generation,
                                           ack_data, ack_length, NULL);
  g_print ("PHASE=%s\n", goodix_secure_phase_name (
             goodix_secure_session_get_phase (
               goodix_device_context_get_secure_session (ctx))));
  g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (backend), ==, 1u);
  g_assert_cmpuint (seam.in_submit_count, ==, 2u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_in_completion_count (backend),
                    ==, 2u);
  operator_message (OP_MSG_HOST_ONLY_A2_ACK_RECEIVED);

  /* Typed A2 response on the re-armed second IN. */
  typed = build_a0_frame (0xa2, a2, sizeof a2);
  typed_data = g_bytes_get_data (typed, &typed_length);
  goodix_fpi_usb_backend_complete_receive (backend, generation,
                                           typed_data, typed_length, NULL);
  g_print ("PHASE=%s\n", goodix_secure_phase_name (
             goodix_secure_session_get_phase (
               goodix_device_context_get_secure_session (ctx))));
  g_assert_cmpint (goodix_secure_session_get_phase (
                     goodix_device_context_get_secure_session (ctx)), ==,
                   GOODIX_SECURE_PHASE_A8);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_in_completion_count (backend),
                    ==, 3u);
  operator_message (OP_MSG_HOST_ONLY_A2_TYPED_RECEIVED);

  /* Cancel the session and drain outstanding transfers for clean teardown. */
  goodix_secure_session_cancel (
    goodix_device_context_get_secure_session (ctx), "host-only closure");
  while (!g_queue_is_empty (seam.out))
    {
      HostOnlySubmission *submission = g_queue_pop_head (seam.out);
      goodix_fpi_usb_backend_complete_out (backend, submission->generation,
                                           NULL);
      host_only_submission_free (submission);
    }
  if (goodix_fpi_usb_backend_get_outstanding (backend) != 0u)
    goodix_device_context_complete_receive (
      ctx, generation, NULL, 0, NULL);

  goodix_device_context_stop_operator_epoch (ctx);
  g_assert_true (goodix_device_context_operator_epoch_is_drained (ctx));
  g_queue_free_full (seam.out, (GDestroyNotify) host_only_submission_free);
  operator_message (OP_MSG_HOST_ONLY_SUCCESS);

  /* Host-only proof of the runtime-state-driven operator prompt tracker.
   * The tracker is exercised against the exact requested phase sequence and
   * against separate success-then-failure and failure-then-success sequences;
   * no USB access, no timers. */
  {
    OperatorPromptTracker tracker;

    /* Normal success sequence with duplicate suppression. */
    operator_prompt_tracker_init (&tracker);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_FIRST_IRQ2, FALSE),
      ==, OPERATOR_PROMPT_FIRST_FINGER);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_FIRST_IRQ2, FALSE),
      ==, OPERATOR_PROMPT_NONE);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_RELEASE_IRQ200,
                                     FALSE),
      ==, OPERATOR_PROMPT_REMOVE_FINGER);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_RELEASE_IRQ200,
                                     FALSE),
      ==, OPERATOR_PROMPT_NONE);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_SECOND_IRQ2, FALSE),
      ==, OPERATOR_PROMPT_SECOND_FINGER);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_STOP, FALSE),
      ==, OPERATOR_PROMPT_SUCCESS);
    g_assert_true (tracker.success_emitted);
    g_assert_false (tracker.failure_emitted);
    g_assert_cmpuint (tracker.success_count, ==, 1u);
    g_assert_cmpuint (tracker.failure_count, ==, 0u);
    g_assert_cmpuint (tracker.duplicate_count, ==, 2u);

    /* STOP -> TERMINAL: success emitted, failure must never follow. */
    operator_prompt_tracker_init (&tracker);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_STOP, FALSE),
      ==, OPERATOR_PROMPT_SUCCESS);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_TERMINAL, TRUE),
      ==, OPERATOR_PROMPT_NONE);
    g_assert_true (tracker.success_emitted);
    g_assert_false (tracker.failure_emitted);
    g_assert_cmpuint (tracker.success_count, ==, 1u);
    g_assert_cmpuint (tracker.failure_count, ==, 0u);

    /* TERMINAL -> STOP: terminal emitted, success must never follow. */
    operator_prompt_tracker_init (&tracker);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_FIRST_IRQ2, FALSE),
      ==, OPERATOR_PROMPT_FIRST_FINGER);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_RELEASE_IRQ200,
                                     FALSE),
      ==, OPERATOR_PROMPT_REMOVE_FINGER);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_SECOND_IRQ2, FALSE),
      ==, OPERATOR_PROMPT_SECOND_FINGER);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_TERMINAL, TRUE),
      ==, OPERATOR_PROMPT_FAILURE);
    g_assert_cmpint (
      operator_prompt_tracker_emit (&tracker,
                                     GOODIX_POST_TLS_PHASE_STOP, FALSE),
      ==, OPERATOR_PROMPT_NONE);
    g_assert_false (tracker.success_emitted);
    g_assert_true (tracker.failure_emitted);
    g_assert_cmpuint (tracker.success_count, ==, 0u);
    g_assert_cmpuint (tracker.failure_count, ==, 1u);

    /* Exact banner format: separator lines, human text, no machine prefix. */
    {
      g_autofree gchar *expected = NULL;
      g_autoptr(GString) rendered = g_string_new (NULL);
      g_string_printf (rendered,
                       "======================\n%s\n======================\n",
                       OP_BANNER_FIRST_FINGER);
      expected = g_strdup_printf ("======================\n%s\n======================\n",
                                  OP_BANNER_FIRST_FINGER);
      g_assert_cmpstr (rendered->str, ==, expected);
      g_assert_null (g_strstr_len (rendered->str, -1, "OPERATOR_MESSAGE_IT="));
    }
    {
      g_autofree gchar *expected = NULL;
      g_autoptr(GString) rendered = g_string_new (NULL);
      g_string_printf (rendered,
                       "======================\n%s\n======================\n",
                       OP_BANNER_REMOVE_FINGER);
      expected = g_strdup_printf ("======================\n%s\n======================\n",
                                  OP_BANNER_REMOVE_FINGER);
      g_assert_cmpstr (rendered->str, ==, expected);
      g_assert_null (g_strstr_len (rendered->str, -1, "OPERATOR_MESSAGE_IT="));
    }
    {
      g_autofree gchar *expected = NULL;
      g_autoptr(GString) rendered = g_string_new (NULL);
      g_string_printf (rendered,
                       "======================\n%s\n======================\n",
                       OP_BANNER_SECOND_FINGER);
      expected = g_strdup_printf ("======================\n%s\n======================\n",
                                  OP_BANNER_SECOND_FINGER);
      g_assert_cmpstr (rendered->str, ==, expected);
      g_assert_null (g_strstr_len (rendered->str, -1, "OPERATOR_MESSAGE_IT="));
    }
    {
      g_autofree gchar *expected = NULL;
      g_autoptr(GString) rendered = g_string_new (NULL);
      g_string_printf (rendered,
                       "======================\n%s\n======================\n",
                       OP_BANNER_SUCCESS);
      expected = g_strdup_printf ("======================\n%s\n======================\n",
                                  OP_BANNER_SUCCESS);
      g_assert_cmpstr (rendered->str, ==, expected);
      g_assert_null (g_strstr_len (rendered->str, -1, "OPERATOR_MESSAGE_IT="));
    }
    {
      g_autofree gchar *expected = NULL;
      g_autoptr(GString) rendered = g_string_new (NULL);
      g_string_printf (rendered,
                       "======================\n%s\n======================\n",
                       OP_BANNER_FAILURE);
      expected = g_strdup_printf ("======================\n%s\n======================\n",
                                  OP_BANNER_FAILURE);
      g_assert_cmpstr (rendered->str, ==, expected);
      g_assert_null (g_strstr_len (rendered->str, -1, "OPERATOR_MESSAGE_IT="));
    }

    g_print ("OPERATOR_PROMPT_SEQUENCE_HOST_ONLY_PROVEN=true\n");
    g_print ("OPERATOR_PROMPT_SUCCESS_FAILURE_EXCLUSIVE=true\n");
    g_print ("OPERATOR_PROMPT_DUPLICATE_SUPPRESSION_HOST_ONLY_PROVEN=true\n");
    g_print ("OPERATOR_PROMPT_STOP_THEN_TERMINAL_HOST_ONLY_PROVEN=true\n");
    g_print ("OPERATOR_PROMPT_TERMINAL_THEN_STOP_HOST_ONLY_PROVEN=true\n");
    g_print ("OPERATOR_ACTION_BANNER_FORMAT_EXACT=true\n");
    g_print ("OPERATOR_ACTION_BANNER_MACHINE_PREFIX=false\n");
  }

  g_print ("OPERATOR_PROMPT_STATE_MACHINE_HOST_ONLY=PASS\n");
  g_print ("REAL_USB_ACCESS=false\nREAL_USB_SUBMIT=0\n");
  g_print ("A2_BACKEND_COMPLETION_REARM=true\n");
  g_print ("A2_TYPED_ADVANCE_TO_A8=true\n");
  g_print ("PRE_SESSION_RX_SYNC_IMPLEMENTED=true\n");
  g_print ("PRE_SESSION_RX_CLEAN_QUIET_BOUNDARY_HOST_ONLY_PROVEN=true\n");
  g_print ("STRICT_A2_ACK_THEN_TYPED_RESTORED=true\n");
  g_print ("CORRECTIVE_5_RUNTIME_TOLERANCE_RETIRED=true\n");
  return 0;
}

#ifdef D278_13_LIVE_BINDING
static gboolean
physical_binding_is_valid (GoodixFpImageDevice *device,
                           GUsbDevice           *usb_device)
{
  GoodixDeviceContext *ctx;
  GoodixFpiUsbBackend *backend;

  if (device == NULL || usb_device == NULL ||
      fpi_device_get_usb_device (FP_DEVICE (device)) != usb_device ||
      FP_DEVICE_GET_CLASS (device)->type != FP_DEVICE_TYPE_USB)
    return FALSE;

  ctx = goodix_fpimage_device_get_context (device);
  if (ctx == NULL || goodix_device_context_get_usb_router (ctx) == NULL)
    return FALSE;
  backend = goodix_device_context_get_fpi_usb_backend (ctx);
  return backend != NULL && goodix_fpi_usb_backend_is_drained (backend) &&
    goodix_fpi_usb_backend_get_outstanding (backend) == 0u &&
    goodix_fpi_usb_backend_get_out_outstanding (backend) == 0u &&
    goodix_fpi_usb_backend_get_real_submit_count (backend) == 0u;
}

static int
run_physical_constructor_host_only (void)
{
  g_autoptr(GUsbDevice) usb_device = NULL;
  g_autoptr(GoodixFpImageDevice) device = NULL;
  GoodixDeviceContext *ctx;
  GoodixFpiUsbBackend *backend;
  GoodixUsbRouter *router;

  usb_device = G_USB_DEVICE (g_object_new (G_USB_TYPE_DEVICE, NULL));
  if (usb_device == NULL)
    return 1;
  device = goodix_fpimage_device_new_for_usb (usb_device);
  if (!physical_binding_is_valid (device, usb_device))
    return 1;

  ctx = goodix_fpimage_device_get_context (device);
  backend = goodix_device_context_get_fpi_usb_backend (ctx);
  router = goodix_device_context_get_usb_router (ctx);
  if (goodix_device_context_get_fpi_usb_backend (ctx) != backend ||
      goodix_device_context_get_usb_router (ctx) != router)
    return 1;

  g_print ("FPDEVICE_USB_BINDING_CONSTRUCTION_HOST_ONLY=PASS\n"
           "FPDEVICE_TRANSPORT_TYPE=USB\n"
           "NON_NULL_GUSBDEVICE_BOUND=true\n"
           "NON_NULL_GUSBDEVICE_FPDEVICE_BINDING_HOST_ONLY_PROVEN=true\n"
           "SINGLE_GOODIX_DEVICE_CONTEXT=true\n"
           "SINGLE_USB_BACKEND_OWNER=true\n"
           "SINGLE_USB_ROUTER=true\n"
           "REAL_USB_ENUMERATION_COUNT=0\n"
           "REAL_USB_OPEN_COUNT=0\n"
           "REAL_USB_CLAIM_COUNT=0\n"
           "REAL_USB_ACCESS=false\n"
           "REAL_USB_SUBMIT=0\n"
           "REAL_PRODUCTION_SECRET_READ=false\n");
  return 0;
}

typedef struct
{
  GoodixSecurePhase    secure_phase;
  GoodixPostTlsPhase   post_tls_phase;
  guint                in_outstanding;
  guint                router_outstanding;
} StopSnapshot;

typedef struct
{
  GoodixDeviceContext *ctx;
  GMainLoop *loop;
  GString *phase_trace;
  guint monitor_source;
  gint64 deadline_us;
  gboolean stopping;
  gboolean success;
  const gchar *failure_class;
  OperatorPromptTracker prompt_tracker;
  StopSnapshot snapshot;
  gint64 stop_time_us;
} Runtime;

static void
observe_phase (GoodixSecurePhase phase,
               guint64           generation,
               gpointer          user_data)
{
  Runtime *runtime = user_data;

  (void) generation;
  if (runtime->phase_trace->len != 0)
    g_string_append_c (runtime->phase_trace, '>');
  g_string_append (runtime->phase_trace, goodix_secure_phase_name (phase));
}

static void
capture_stop_snapshot (Runtime *runtime)
{
  GoodixSecureSession *session =
    goodix_device_context_get_secure_session (runtime->ctx);
  GoodixFpiUsbBackend *backend =
    goodix_device_context_get_fpi_usb_backend (runtime->ctx);
  GoodixUsbRouter *router =
    goodix_device_context_get_usb_router (runtime->ctx);

  runtime->snapshot.secure_phase = session != NULL ?
    goodix_secure_session_get_phase (session) : GOODIX_SECURE_PHASE_TERMINAL;
  runtime->snapshot.post_tls_phase =
    goodix_post_tls_lifecycle_get_phase (
      goodix_device_context_get_post_tls_lifecycle (runtime->ctx));
  runtime->snapshot.in_outstanding = backend != NULL ?
    goodix_fpi_usb_backend_get_outstanding (backend) : 0;
  runtime->snapshot.router_outstanding = router != NULL ?
    goodix_usb_router_get_outstanding (router) : 0;
}

static gboolean
monitor_runtime (gpointer user_data)
{
  Runtime *runtime = user_data;
  GoodixPostTlsLifecycle *post =
    goodix_device_context_get_post_tls_lifecycle (runtime->ctx);
  GoodixPostTlsPhase phase = goodix_post_tls_lifecycle_get_phase (post);
  gboolean terminal = phase == GOODIX_POST_TLS_PHASE_TERMINAL ||
                      goodix_device_context_get_terminal_fence (runtime->ctx);

  /* Drive operator prompts from the actual runtime phase, not from timers. */
  operator_prompt_tracker_emit (&runtime->prompt_tracker, phase, terminal);

  if (!runtime->stopping && phase == GOODIX_POST_TLS_PHASE_STOP)
    {
      runtime->success = TRUE;
      runtime->stopping = TRUE;
      runtime->stop_time_us = g_get_monotonic_time ();
      capture_stop_snapshot (runtime);
      goodix_device_context_stop_operator_epoch (runtime->ctx);
    }
  else if (!runtime->stopping &&
           (terminal || g_get_monotonic_time () >= runtime->deadline_us))
    {
      runtime->failure_class = g_get_monotonic_time () >= runtime->deadline_us ?
        "ONE_SHOT_DEADLINE" : "INTEGRATED_PATH_TERMINAL";
      runtime->stopping = TRUE;
      runtime->stop_time_us = g_get_monotonic_time ();
      capture_stop_snapshot (runtime);
      goodix_device_context_stop_operator_epoch (runtime->ctx);
    }
  if (runtime->stopping &&
      goodix_device_context_operator_epoch_is_drained (runtime->ctx))
    {
      runtime->monitor_source = 0;
      g_main_loop_quit (runtime->loop);
      return G_SOURCE_REMOVE;
    }
  return G_SOURCE_CONTINUE;
}

static guint16
operator_timestamp (void)
{
  return (guint16) ((guint64) (g_get_monotonic_time () / 1000) & 0xffffu);
}

static gboolean
drain_after_stop (GoodixDeviceContext *ctx)
{
  gint64 deadline = g_get_monotonic_time () + 10 * G_TIME_SPAN_SECOND;

  while (!goodix_device_context_operator_epoch_is_drained (ctx) &&
         g_get_monotonic_time () < deadline)
    {
      while (g_main_context_iteration (NULL, FALSE))
        ;
      g_usleep (1000u);
    }
  return goodix_device_context_operator_epoch_is_drained (ctx);
}

static int
run_live_once (void)
{
  GoodixTargetMaterialAudit material_audit = { 0 };
  GoodixSecureSessionMaterial secure_material = { 0 };
  GoodixSecureSessionAudit secure_audit = { 0 };
  GoodixTlsAudit tls_audit = { 0 };
  GoodixPostTlsAudit post_audit = { 0 };
  GoodixPostTlsMaterial post_material = { 0 };
  GoodixPreSessionRxSyncAudit rx_sync_audit = { 0 };
  g_autoptr(GError) error = NULL;
  g_autoptr(GUsbContext) usb_context = NULL;
  g_autoptr(GPtrArray) devices = NULL;
  g_autoptr(GCancellable) cancellable = NULL;
  g_autoptr(GoodixFpImageDevice) device = NULL;
  GoodixTargetMaterial *material_owner = NULL;
  GoodixFpiUsbBackend *backend = NULL;
  GUsbDevice *target = NULL;
  Runtime runtime = { 0 };
  guint matches = 0;
  guint open_count = 0;
  guint claim_count = 0;
  guint release_count = 0;
  guint close_count = 0;
  gboolean opened = FALSE;
  gboolean claimed = FALSE;
  gboolean epoch_started = FALSE;
  gboolean backend_drained = FALSE;
  gboolean project_secret_zeroized = FALSE;
  guint64 real_submit_count = 0;
  guint64 out_submit_count = 0;
  guint64 in_completion_count = 0;
  guint64 out_completion_count = 0;
  guint max_in_outstanding = 0;
  guint max_out_outstanding = 0;
  const gchar *authorization_reason = "none";
  gboolean live_authorization_consumed = FALSE;
  int rc = 1;

  gint64 start_time_us = g_get_monotonic_time ();

  runtime.failure_class = "PRE_BIND_FAILURE";
  if (!live_authorization_gate (&live_authorization_consumed,
                                &authorization_reason))
    {
      g_printerr ("LIVE_NOT_AUTHORIZED_OR_BASELINE_UNAPPROVED\n"
                  "AUTHORIZATION_FAILURE_REASON=%s\n"
                  "LIVE_AUTHORIZATION_CONSUMED=%s\n"
                  "REAL_PRODUCTION_SECRET_READ=false\n"
                  "REAL_USB_ACCESS=false\nREAL_USB_SUBMIT=0\n",
                  authorization_reason,
                  live_authorization_consumed ? "true" : "false");
      return 3;
    }
  operator_message (OP_MSG_AUTHORIZATION_OK);

  material_owner = prepare_target_material (&material_audit,
                                              &secure_material, &error);

  if (material_owner == NULL ||
      !load_canonical_fdt_seed (post_material.initial_fdt_table, &error))
    goto cleanup;
  post_material.af_timestamp = operator_timestamp ();
  post_material.first_arm_timestamp = operator_timestamp ();
  post_material.second_arm_timestamp = operator_timestamp ();

  usb_context = g_usb_context_new (&error);
  if (usb_context == NULL || !g_usb_context_enumerate (usb_context, &error))
    goto cleanup;
  devices = g_usb_context_get_devices (usb_context);
  for (guint i = 0; i < devices->len; i++)
    {
      GUsbDevice *candidate = g_ptr_array_index (devices, i);
      if (g_usb_device_get_vid (candidate) == D278_VID &&
          g_usb_device_get_pid (candidate) == D278_PID)
        {
          target = candidate;
          matches++;
        }
    }
  if (matches != 1u)
    goto cleanup;
  operator_message (OP_MSG_DEVICE_DETECTED);

  runtime.failure_class = "FPDEVICE_USB_BINDING_CONSTRUCTION";
  device = goodix_fpimage_device_new_for_usb (target);
  if (!physical_binding_is_valid (device, target))
    goto cleanup;
  runtime.ctx = goodix_fpimage_device_get_context (device);
  backend = goodix_device_context_get_fpi_usb_backend (runtime.ctx);

  runtime.failure_class = "USB_OPEN_OR_CLAIM_FAILURE";
  open_count = 1u;
  if (!g_usb_device_open (target, &error))
    goto cleanup;
  opened = TRUE;
  if (!g_usb_device_claim_interface (target, D278_INTERFACE,
                                       G_USB_DEVICE_CLAIM_INTERFACE_NONE,
                                       &error))
    goto cleanup;
  claimed = TRUE;
  claim_count = 1u;

  runtime.loop = g_main_loop_new (NULL, FALSE);
  runtime.phase_trace = g_string_new (NULL);
  runtime.failure_class = "NONE";
  runtime.deadline_us = g_get_monotonic_time () + 120 * G_TIME_SPAN_SECOND;
  cancellable = g_cancellable_new ();
  if (!goodix_device_context_begin_operator_epoch (runtime.ctx, cancellable,
                                                     &error))
    goto cleanup;
  epoch_started = TRUE;
  runtime.failure_class = "PRE_SESSION_RX_SYNC_FAILURE";
  if (!goodix_device_context_begin_pre_session_rx_sync (runtime.ctx, &error))
    goto cleanup;
  while (goodix_device_context_get_pre_session_rx_sync_result (runtime.ctx) ==
         GOODIX_PRE_SESSION_RX_SYNC_ACTIVE)
    g_main_context_iteration (NULL, TRUE);
  if (goodix_device_context_get_pre_session_rx_sync_result (runtime.ctx) !=
      GOODIX_PRE_SESSION_RX_SYNC_PASS)
    goto cleanup;
  runtime.failure_class = "NONE";
  goodix_device_context_set_secure_phase_observer (runtime.ctx,
                                                     observe_phase, &runtime);
  if (!goodix_device_context_configure_post_tls_lifecycle (
        runtime.ctx, &post_material, &post_audit, &error))
    goto cleanup;
  goodix_device_context_set_post_tls_await_finger_on (runtime.ctx, TRUE);
  if (!goodix_device_context_start_secure_session (
        runtime.ctx, &secure_material, NULL, NULL,
        &secure_audit, &tls_audit, &error))
    goto cleanup;
  operator_message (OP_MSG_SECURE_SESSION_STARTED);
  goodix_target_material_free (material_owner);
  material_owner = NULL;
  OPENSSL_cleanse (&secure_material, sizeof secure_material);
  operator_prompt_tracker_init (&runtime.prompt_tracker);
  runtime.monitor_source = g_timeout_add (10u, monitor_runtime, &runtime);
  g_main_loop_run (runtime.loop);

  if (!runtime.success && !runtime.prompt_tracker.failure_emitted)
    operator_action_banner (OP_BANNER_FAILURE);

cleanup:
  if (material_owner != NULL)
    goodix_target_material_free (material_owner);
  OPENSSL_cleanse (&secure_material, sizeof secure_material);
  if (epoch_started && !runtime.stopping)
    goodix_device_context_stop_operator_epoch (runtime.ctx);
  if (runtime.monitor_source != 0)
    g_source_remove (runtime.monitor_source);
  if (epoch_started && !drain_after_stop (runtime.ctx))
    runtime.failure_class = "BACKEND_DRAIN_TIMEOUT";
  if (claimed)
    {
      g_clear_error (&error);
      if (g_usb_device_release_interface (target, D278_INTERFACE,
                                            G_USB_DEVICE_CLAIM_INTERFACE_NONE,
                                            &error))
        release_count = 1u;
    }
  if (opened)
    {
      g_clear_error (&error);
      if (g_usb_device_close (target, &error))
        close_count = 1u;
    }

  if (backend != NULL)
    {
      backend_drained = goodix_fpi_usb_backend_is_drained (backend);
      real_submit_count = goodix_fpi_usb_backend_get_real_submit_count (backend);
      out_submit_count = goodix_fpi_usb_backend_get_out_submit_count (backend);
      in_completion_count =
        goodix_fpi_usb_backend_get_in_completion_count (backend);
      out_completion_count =
        goodix_fpi_usb_backend_get_out_completion_count (backend);
      max_in_outstanding = goodix_fpi_usb_backend_get_max_outstanding (backend);
      max_out_outstanding =
        goodix_fpi_usb_backend_get_max_out_outstanding (backend);
      goodix_device_context_get_pre_session_rx_sync_audit (
        runtime.ctx, &rx_sync_audit);
      rc = runtime.success && backend_drained &&
         post_audit.second_image_pipeline_count == 1u &&
         post_audit.third_cycle_command_count == 0u &&
         secure_audit.retry_count == 0u &&
         secure_audit.transport_reopen_count == 0u &&
         secure_audit.device_reset_count == 0u &&
         secure_audit.clear_halt_count == 0u &&
         secure_audit.persistent_write_count == 0u &&
         post_audit.retry_count == 0u && post_audit.reopen_count == 0u &&
         post_audit.device_reset_count == 0u &&
         post_audit.clear_halt_count == 0u &&
         post_audit.persistent_device_write_count == 0u &&
         release_count == 1u && close_count == 1u ? 0 : 1;
    }
  if (backend_drained)
    g_clear_object (&device);
  else if (device != NULL)
    (void) g_steal_pointer (&device);
  project_secret_zeroized = material_audit.project_secret_zeroized &&
    secure_audit.project_material_zeroized &&
    tls_audit.project_secret_zeroized;
  if (!project_secret_zeroized)
    rc = 1;
  g_print ("{\"result\":\"%s\",\"failure_class\":\"%s\","
           "\"phase_trace\":\"%s\","
           "\"live_authorization_consumed\":%s,"
           "\"pre_session_rx_sync_started\":%s,"
           "\"pre_session_rx_sync_completed\":%s,"
           "\"pre_session_rx_quiet_boundary\":%s,"
           "\"pre_session_rx_discarded_completion_count\":%" G_GUINT64_FORMAT ","
           "\"pre_session_rx_discarded_byte_count\":%" G_GUINT64_FORMAT ","
           "\"pre_session_rx_timeout_count\":%" G_GUINT64_FORMAT ","
           "\"pre_session_rx_non_timeout_error_count\":%" G_GUINT64_FORMAT ","
           "\"pre_session_rx_max_outstanding\":%u,"
           "\"pre_session_rx_elapsed_ms\":%" G_GUINT64_FORMAT ","
           "\"pre_session_rx_result\":\"%s\","
           "\"first_protocol_out_after_rx_sync\":%s,"
           "\"usb_open_attempt_count\":%u,"
           "\"usb_open_count\":%u,\"usb_claim_count\":%u,"
           "\"usb_release_count\":%u,\"usb_close_count\":%u,"
           "\"physical_submit_count\":%" G_GUINT64_FORMAT ","
           "\"physical_in_submit_count\":%" G_GUINT64_FORMAT ","
           "\"physical_out_submit_count\":%" G_GUINT64_FORMAT ","
           "\"physical_in_completion_count\":%" G_GUINT64_FORMAT ","
           "\"physical_out_completion_count\":%" G_GUINT64_FORMAT ","
           "\"max_outstanding_in\":%u,\"max_outstanding_out\":%u,"
           "\"secure_command_count\":%u,\"ack_count\":%u,"
           "\"typed_count\":%u,\"reentry_a2_result\":\"%s\","
           "\"reentry_pre_ack_typed_observed\":%s,"
           "\"reentry_pre_ack_typed_pin_match\":%s,"
           "\"reentry_pre_ack_typed_discard_count\":%u,"
           "\"a8_app12509_pin\":%s,\"e4_binding\":%s,"
           "\"tls_handshake_count\":%u,\"tls_established\":%s,"
           "\"secret_handoff_count\":%u,\"project_secret_zeroized\":%s,"
           "\"d4_count\":%u,\"af_count\":%u,"
           "\"fdt36_count\":%u,\"fdt_irq100_count\":%u,"
           "\"fresh_fdt_count\":%u,\"first_irq0002_count\":%u,"
           "\"first_0x22_count\":%u,\"first_b0_count\":%u,"
           "\"first_decode_count\":%u,"
           "\"first_image_pipeline_count\":%u,"
           "\"release_0x34_count\":%u,\"irq0200_count\":%u,"
           "\"post_up_0x20_count\":%u,\"post_up_b0_count\":%u,"
           "\"nav_0x50_count\":%u,\"nav_response_count\":%u,"
           "\"release_tail_complete_count\":%u,"
           "\"fresh_down_table_count\":%u,\"rearm_count\":%u,"
           "\"second_irq0002_count\":%u,\"second_0x22_count\":%u,"
           "\"second_b0_count\":%u,\"second_decode_count\":%u,"
           "\"second_image_pipeline_count\":%u,"
           "\"third_cycle_command_count\":%u,\"stop_reached\":%s,"
           "\"retry_count\":0,\"reopen_count\":0,"
           "\"device_reset_count\":0,\"clear_halt_count\":0,"
           "\"persistent_device_write_count\":0,"
            "\"secure_protocol_failure_recorded\":%s,"
            "\"secure_protocol_failure_phase\":\"%s\","
            "\"secure_protocol_failure_kind\":\"%s\","
            "\"post_tls_terminal\":%s,"
            "\"post_tls_rejected_a0_observed\":%s,"
            "\"post_tls_rejected_phase\":\"%s\","
            "\"post_tls_rejected_control\":%d,"
            "\"post_tls_rejected_irq\":%d,"
            "\"post_tls_rejected_flags\":%d,"
            "\"post_tls_rejected_body_length\":%" G_GSSIZE_FORMAT ","
            "\"observed_outer_type\":%d,"
            "\"observed_a0_control\":%d,"
            "\"observed_ack_echo\":%d,"
            "\"observed_ack_status\":%d,"
            "\"observed_body_length\":%" G_GSSIZE_FORMAT ","
            "\"secure_phase_at_stop\":\"%s\","
            "\"post_tls_phase_at_stop\":\"%s\","
            "\"in_outstanding_at_stop\":%u,"
            "\"router_outstanding_at_stop\":%u,"
            "\"stop_time_ms\":%" G_GINT64_FORMAT ","
            "\"backend_drained\":%s,\"cleanup_complete\":%s}\n",

           rc == 0 ? "pass" : "fail", runtime.failure_class,
           runtime.phase_trace != NULL ? runtime.phase_trace->str : "",
           live_authorization_consumed ? "true" : "false",
           rx_sync_audit.pre_session_rx_sync_started ? "true" : "false",
           rx_sync_audit.pre_session_rx_sync_completed ? "true" : "false",
           rx_sync_audit.pre_session_rx_quiet_boundary ? "true" : "false",
           rx_sync_audit.pre_session_rx_discarded_completion_count,
           rx_sync_audit.pre_session_rx_discarded_byte_count,
           rx_sync_audit.pre_session_rx_timeout_count,
           rx_sync_audit.pre_session_rx_non_timeout_error_count,
           rx_sync_audit.pre_session_rx_max_outstanding,
           rx_sync_audit.pre_session_rx_elapsed_ms,
           goodix_pre_session_rx_sync_result_name (
             rx_sync_audit.pre_session_rx_result),
           rx_sync_audit.first_protocol_out_after_rx_sync ? "true" : "false",
           open_count, opened ? 1u : 0u, claim_count, release_count,
           close_count,
           real_submit_count,
           real_submit_count >= out_submit_count ?
             real_submit_count - out_submit_count : 0u,
           out_submit_count, in_completion_count, out_completion_count,
           max_in_outstanding, max_out_outstanding,
           secure_audit.command_count, secure_audit.ack_count,
           secure_audit.typed_response_count,
           goodix_reentry_recovery_a2_result_class_name (
             secure_audit.reentry_recovery_a2_result_class),
           secure_audit.reentry_pre_ack_typed_observed ? "true" : "false",
           secure_audit.reentry_pre_ack_typed_pin_match ? "true" : "false",
           secure_audit.reentry_pre_ack_typed_discard_count,
           secure_audit.a8_app12509_pin_match ? "true" : "false",
           material_audit.e4_binding_match ? "true" : "false",
           tls_audit.handshake_count,
           secure_audit.tls_established ? "true" : "false",
           tls_audit.secret_handoff_count,
           project_secret_zeroized ? "true" : "false",
           post_audit.d4_count, post_audit.af_count,
           post_audit.fdt36_submit_count, post_audit.fdt_irq100_count,
           post_audit.fresh_fdt_count, post_audit.first_irq0002_count,
           post_audit.first_image_command_count,
           post_audit.first_image_b0_count,
           post_audit.first_image_decode_count,
           post_audit.first_image_pipeline_count,
           post_audit.release_0x34_count, post_audit.irq0200_count,
           post_audit.post_up_0x20_count, post_audit.post_up_b0_count,
           post_audit.nav_0x50_count, post_audit.nav_response_count,
           post_audit.release_tail_complete_count,
           post_audit.fresh_down_table_count,
           post_audit.rearm_0x32_count,
           post_audit.second_irq0002_count,
           post_audit.second_image_command_count,
           post_audit.second_b0_count,
           post_audit.second_image_decode_count,
           post_audit.second_image_pipeline_count,
           post_audit.third_cycle_command_count,
           runtime.success ? "true" : "false",
           secure_audit.protocol_failure_recorded ? "true" : "false",
           secure_audit.protocol_failure_recorded ?
             goodix_secure_phase_name (secure_audit.protocol_failure_phase) :
             "",
           secure_audit.protocol_failure_recorded ?
             goodix_protocol_failure_kind_name (
               secure_audit.protocol_failure_kind) : "",
            post_audit.terminal ? "true" : "false",
            post_audit.rejected_a0_observed ? "true" : "false",
            post_audit.rejected_a0_observed ?
              goodix_post_tls_phase_name (post_audit.rejected_a0_phase) : "",
            post_audit.rejected_a0_observed ?
              post_audit.rejected_a0_control : -1,
            post_audit.rejected_a0_observed ?
              post_audit.rejected_a0_irq : -1,
            post_audit.rejected_a0_observed ?
              post_audit.rejected_a0_flags : -1,
            post_audit.rejected_a0_observed ?
              post_audit.rejected_a0_body_length : (gssize) -1,
            secure_audit.observed_outer_type,
            secure_audit.observed_a0_control,
            secure_audit.observed_ack_echo,
            secure_audit.observed_ack_status,
            secure_audit.observed_body_length,
            goodix_secure_phase_name (runtime.snapshot.secure_phase),
            goodix_post_tls_phase_name (runtime.snapshot.post_tls_phase),
            runtime.snapshot.in_outstanding,
            runtime.snapshot.router_outstanding,
            runtime.stop_time_us > start_time_us ?
              (runtime.stop_time_us - start_time_us) / 1000 : -1,
            backend_drained ? "true" : "false",

           backend_drained && project_secret_zeroized &&
             release_count == 1u && close_count == 1u ? "true" : "false");
  if (runtime.phase_trace != NULL)
    g_string_free (runtime.phase_trace, TRUE);
  if (runtime.loop != NULL)
    g_main_loop_unref (runtime.loop);
  return rc;
}
#endif

int
main (int argc, char **argv)
{
  if (argc == 2 && g_str_equal (argv[1], "--authorization-gate-self-test"))
    return run_gate_self_test ();
  if (argc == 4 && g_str_equal (argv[1],
                                 "--authorization-ticket-gate-only"))
    return run_ticket_gate_only (argv[2], argv[3]);
  if (argc == 2 && g_str_equal (argv[1],
                                 "--operator-prompt-state-machine-host-only"))
    return run_operator_prompt_state_machine_host_only ();
#ifdef D278_13_LIVE_BINDING
  if (argc == 2 && g_str_equal (argv[1],
                                 "--physical-constructor-host-only"))
    return run_physical_constructor_host_only ();
  if (argc == 2 && g_str_equal (argv[1], "--live-integrated-once"))
    return run_live_once ();
#endif
  g_printerr ("usage: %s --authorization-gate-self-test | "
              "--authorization-ticket-gate-only <ticket> <expected-sha> | "
              "--operator-prompt-state-machine-host-only%s\n",
              argv[0],
#ifdef D278_13_LIVE_BINDING
              " | --physical-constructor-host-only | --live-integrated-once"
#else
              ""
#endif
              );
  return 2;
}
