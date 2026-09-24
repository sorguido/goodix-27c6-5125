/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "goodix_target_material.h"

#include "goodix_action_binding.h"

#include <errno.h>
#include <fcntl.h>
#include <openssl/crypto.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

typedef enum
{
  GOODIX_TARGET_MATERIAL_ERROR_ARGUMENT,
  GOODIX_TARGET_MATERIAL_ERROR_OPEN,
  GOODIX_TARGET_MATERIAL_ERROR_METADATA,
  GOODIX_TARGET_MATERIAL_ERROR_READ,
  GOODIX_TARGET_MATERIAL_ERROR_CONTENT,
  GOODIX_TARGET_MATERIAL_ERROR_BINDING,
  GOODIX_TARGET_MATERIAL_ERROR_STATE,
} GoodixTargetMaterialError;

#define GOODIX_TARGET_MATERIAL_ERROR (goodix_target_material_error_quark ())

struct _GoodixTargetMaterial
{
  GoodixTargetMaterialPolicy policy;
  GoodixTargetMaterialAudit *audit;
  guint8 *psk;
  guint8 transport_validator[32];
  guint8 *config90;
  guint8 *validator;
  gboolean bound;
};

static const guint8 app12509_identity[] = "GF_ST411SEC_APP_12509";

static GQuark
goodix_target_material_error_quark (void)
{
  return g_quark_from_static_string ("goodix-target-material-error");
}

const gchar *
goodix_target_material_error_class (const GError *error)
{
  if (error == NULL || error->domain != GOODIX_TARGET_MATERIAL_ERROR)
    return "ARGUMENT_OR_POLICY";

  switch ((GoodixTargetMaterialError) error->code)
    {
    case GOODIX_TARGET_MATERIAL_ERROR_OPEN:
      return "PROTECTED_OPEN";
    case GOODIX_TARGET_MATERIAL_ERROR_METADATA:
      return "PROTECTED_METADATA";
    case GOODIX_TARGET_MATERIAL_ERROR_READ:
      return "PROTECTED_READ";
    case GOODIX_TARGET_MATERIAL_ERROR_CONTENT:
      return "PROTECTED_CONTENT";
    case GOODIX_TARGET_MATERIAL_ERROR_BINDING:
      return "E4_BINDING";
    case GOODIX_TARGET_MATERIAL_ERROR_STATE:
      return "MATERIAL_EXPORT_OR_STATE";
    case GOODIX_TARGET_MATERIAL_ERROR_ARGUMENT:
    default:
      return "ARGUMENT_OR_POLICY";
    }
}

static gboolean
digest (const guint8 *data,
        gsize         length,
        guint8        output[32])
{
  g_autoptr(GChecksum) checksum = g_checksum_new (G_CHECKSUM_SHA256);
  gsize output_length = 32;

  if (length > G_MAXSSIZE)
    return FALSE;
  g_checksum_update (checksum, data, (gssize) length);
  g_checksum_get_digest (checksum, output, &output_length);
  return output_length == 32;
}

static void
observe_cleansed (const GoodixTargetMaterialPolicy *policy,
                  const gchar                      *label,
                  const guint8                     *bytes,
                  gsize                             length)
{
  if (policy->cleanse_observer != NULL)
    policy->cleanse_observer (label, bytes, length,
                              policy->cleanse_observer_data);
}

static void
cleanse_free (const GoodixTargetMaterialPolicy *policy,
              const gchar                      *label,
              guint8                           *bytes,
              gsize                             length)
{
  if (bytes == NULL)
    return;
  OPENSSL_cleanse (bytes, length);
  observe_cleansed (policy, label, bytes, length);
  g_free (bytes);
}

void
goodix_target_material_policy_production (GoodixTargetMaterialPolicy *policy)
{
  static const guint16 registers[4] = { 0x0220, 0x0236, 0x0238, 0x023a };
  static const guint offsets[4] = { 117, 121, 125, 129 };

  g_return_if_fail (policy != NULL);
  memset (policy, 0, sizeof *policy);
  policy->owner_uid = 0;
  policy->owner_gid = 0;
  policy->mode = 0600;
  policy->manifest_length = 0;
  policy->transport_length = GOODIX_TARGET_TRANSPORT_LENGTH;
  policy->config90_length = GOODIX_SECURE_SESSION_CONFIG90_LENGTH;
  memcpy (policy->dac_registers, registers, sizeof registers);
  memcpy (policy->dac_offsets, offsets, sizeof offsets);
}

static gboolean
policy_shape_valid (const GoodixTargetMaterialPolicy *policy)
{
  static const guint16 registers[4] = { 0x0220, 0x0236, 0x0238, 0x023a };
  static const guint offsets[4] = { 117, 121, 125, 129 };

  return policy != NULL && policy->mode == 0600 &&
         policy->manifest_length <= GOODIX_TARGET_MANIFEST_MAX_LENGTH &&
         policy->transport_length == GOODIX_TARGET_TRANSPORT_LENGTH &&
         policy->config90_length == GOODIX_SECURE_SESSION_CONFIG90_LENGTH &&
         memcmp (policy->dac_registers, registers, sizeof registers) == 0 &&
         memcmp (policy->dac_offsets, offsets, sizeof offsets) == 0;
}

static gboolean
metadata_valid (const struct stat                 *status,
                const GoodixTargetMaterialPolicy *policy,
                gsize                             expected_length)
{
  return S_ISREG (status->st_mode) && status->st_uid == policy->owner_uid &&
         status->st_gid == policy->owner_gid &&
         (status->st_mode & 07777) == policy->mode &&
         status->st_size > 0 &&
         (expected_length == 0 ?
          (guint64) status->st_size <= GOODIX_TARGET_MANIFEST_MAX_LENGTH :
          (guint64) status->st_size == expected_length);
}

static guint8 *
read_exact_protected (const gchar                      *path,
                      gsize                             expected_length,
                      gboolean                          sensitive,
                      const GoodixTargetMaterialPolicy *policy,
                      GoodixTargetMaterialAudit        *audit,
                      gsize                            *actual_length,
                      GError                          **error)
{
  struct stat before;
  struct stat after;
  guint8 *buffer = NULL;
  gsize offset = 0;
  gint fd = -1;

  fd = open (path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (fd < 0)
    {
      g_set_error (error, GOODIX_TARGET_MATERIAL_ERROR,
                   GOODIX_TARGET_MATERIAL_ERROR_OPEN,
                   "protected open failed: %s", g_strerror (errno));
      goto fail;
    }
  if (audit != NULL)
    audit->protected_open_count++;
  if (fstat (fd, &before) != 0 ||
      !metadata_valid (&before, policy, expected_length))
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_METADATA,
                           "protected file type/uid/gid/mode/size mismatch");
      goto fail;
    }
  if (expected_length == 0)
    expected_length = (gsize) before.st_size;
  buffer = g_malloc0 (expected_length + 1u);
  while (offset < expected_length)
    {
      ssize_t count = read (fd, buffer + offset, expected_length - offset);
      if (count < 0 && errno == EINTR)
        continue;
      if (count <= 0)
        {
          g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                               GOODIX_TARGET_MATERIAL_ERROR_READ,
                               "protected file short/error read");
          goto fail;
        }
      offset += (gsize) count;
    }
  if (policy->after_read != NULL)
    policy->after_read (path, fd, policy->after_read_data);
  if (fstat (fd, &after) != 0 ||
      before.st_dev != after.st_dev || before.st_ino != after.st_ino ||
      before.st_size != after.st_size ||
      !metadata_valid (&after, policy, expected_length))
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_METADATA,
                           "protected file changed during read");
      goto fail;
    }
  if (audit != NULL)
    audit->protected_read_count++;
  if (actual_length != NULL)
    *actual_length = expected_length;
  close (fd);
  return buffer;

fail:
  if (fd >= 0)
    close (fd);
  if (buffer != NULL)
    {
      if (sensitive)
        {
          OPENSSL_cleanse (buffer, expected_length);
          observe_cleansed (policy, "psk-scratch", buffer, expected_length);
          if (audit != NULL)
            {
              audit->psk_scratch_cleanse_count++;
              audit->psk_scratch_cleansed = TRUE;
            }
        }
      g_free (buffer);
    }
  return NULL;
}

static gboolean
hex_digest (const gchar *value,
            guint8       output[32])
{
  if (value == NULL || strlen (value) != 64u)
    return FALSE;
  for (guint i = 0; i < 32u; i++)
    {
      gint high = g_ascii_xdigit_value (value[i * 2u]);
      gint low = g_ascii_xdigit_value (value[i * 2u + 1u]);
      if (high < 0 || low < 0)
        return FALSE;
      output[i] = (guint8) ((high << 4) | low);
    }
  return TRUE;
}

static void
manifest_skip_whitespace (const gchar **cursor,
                          const gchar  *end)
{
  while (*cursor < end &&
         (**cursor == ' ' || **cursor == '\t' ||
          **cursor == '\r' || **cursor == '\n'))
    (*cursor)++;
}

static gchar *
manifest_parse_string (const gchar **cursor,
                       const gchar  *end)
{
  const gchar *start;

  if (*cursor >= end || **cursor != '"')
    return NULL;
  (*cursor)++;
  start = *cursor;
  while (*cursor < end && **cursor != '"')
    {
      if (**cursor == '\\' || (guchar) **cursor < 0x20u)
        return NULL;
      (*cursor)++;
    }
  if (*cursor >= end)
    return NULL;
  (*cursor)++;
  return g_strndup (start, (gsize) ((*cursor - 1) - start));
}

static gboolean
parse_manifest (const guint8               *bytes,
                gsize                       length,
                GoodixTargetMaterialPolicy *policy)
{
  static const gchar *const keys[] = {
    "schema", "vid", "pid", "app",
    "transport_sha256", "config90_sha256", "fdt_cache_sha256",
    "a2_response_sha256", "chip82_response_sha256", "otp_a6_response_sha256"
  };
  guint8 *hash_outputs[] = {
    policy->transport_sha256, policy->config90_sha256,
    policy->fdt_cache_sha256, policy->a2_response_sha256,
    policy->chip82_response_sha256, policy->otp_a6_response_sha256
  };
  gchar *values[G_N_ELEMENTS (keys)] = { NULL };
  const gchar *cursor;
  const gchar *end;
  gboolean ok = FALSE;

  if (bytes == NULL || length == 0u || memchr (bytes, 0, length) != NULL)
    return FALSE;
  cursor = (const gchar *) bytes;
  end = cursor + length;
  manifest_skip_whitespace (&cursor, end);
  if (cursor >= end || *cursor++ != '{')
    goto out;
  manifest_skip_whitespace (&cursor, end);
  if (cursor >= end || *cursor == '}')
    goto out;

  while (cursor < end)
    {
      g_autofree gchar *key = NULL;
      g_autofree gchar *value = NULL;
      guint index;

      key = manifest_parse_string (&cursor, end);
      if (key == NULL)
        goto out;
      for (index = 0; index < G_N_ELEMENTS (keys); index++)
        if (g_str_equal (key, keys[index]))
          break;
      if (index == G_N_ELEMENTS (keys) || values[index] != NULL)
        goto out;
      manifest_skip_whitespace (&cursor, end);
      if (cursor >= end || *cursor++ != ':')
        goto out;
      manifest_skip_whitespace (&cursor, end);
      value = manifest_parse_string (&cursor, end);
      if (value == NULL)
        goto out;
      values[index] = g_steal_pointer (&value);
      manifest_skip_whitespace (&cursor, end);
      if (cursor >= end)
        goto out;
      if (*cursor == '}')
        {
          cursor++;
          break;
        }
      if (*cursor++ != ',')
        goto out;
      manifest_skip_whitespace (&cursor, end);
    }

  manifest_skip_whitespace (&cursor, end);
  if (cursor != end)
    goto out;
  for (guint i = 0; i < G_N_ELEMENTS (keys); i++)
    if (values[i] == NULL)
      goto out;
  if (g_strcmp0 (values[0], "goodix-5125-device-materials-v1") != 0 ||
      g_strcmp0 (values[1], "27c6") != 0 ||
      g_strcmp0 (values[2], "5125") != 0 ||
      g_strcmp0 (values[3], "GF_ST411SEC_APP_12509") != 0)
    goto out;
  for (guint i = 0; i < G_N_ELEMENTS (hash_outputs); i++)
    if (!hex_digest (values[i + 4u], hash_outputs[i]))
      goto out;
  ok = TRUE;

out:
  for (guint i = 0; i < G_N_ELEMENTS (values); i++)
    g_free (values[i]);
  return ok;
}

static gboolean
config_finalizer_valid (const guint8                     *config,
                        const GoodixTargetMaterialPolicy *policy)
{
  guint32 sum = 0;
  guint16 expected;
  guint16 actual;

  for (guint i = 0; i < 111; i++)
    sum += (guint32) config[i * 2u] |
           ((guint32) config[i * 2u + 1u] << 8);
  expected = (guint16) (0u - 0xa5a5u - sum);
  actual = (guint16) config[222] | ((guint16) config[223] << 8);
  return actual == expected &&
         ((policy->config90_finalizer[0] == 0u &&
           policy->config90_finalizer[1] == 0u) ||
          CRYPTO_memcmp (config + 222, policy->config90_finalizer, 2u) == 0);
}

static gboolean
config_correlations_valid (const guint8                     *config,
                           const GoodixTargetMaterialPolicy *policy)
{
  for (guint i = 0; i < 4; i++)
    {
      guint offset = policy->dac_offsets[i];
      guint16 register_value = policy->dac_registers[i];

      if (offset > GOODIX_SECURE_SESSION_CONFIG90_LENGTH - 4u ||
          config[offset] != (guint8) register_value ||
          config[offset + 1u] != (guint8) (register_value >> 8) ||
          memcmp (config + offset + 2u, policy->dac_values[i], 2) != 0)
        return FALSE;
    }
  return TRUE;
}

GoodixTargetMaterial *
goodix_target_material_load (const gchar                      *manifest_path,
                             const gchar                      *transport_path,
                             const gchar                      *config90_path,
                             const GoodixTargetMaterialPolicy *policy,
                             GoodixTargetMaterialAudit        *audit,
                             GError                          **error)
{
  GoodixTargetMaterial *material = NULL;
  guint8 *manifest = NULL;
  guint8 *transport = NULL;
  guint8 *config = NULL;
  guint8 actual[32] = { 0 };
  gsize manifest_length = 0;

  if (audit != NULL)
    memset (audit, 0, sizeof *audit);
  if (manifest_path == NULL || transport_path == NULL || config90_path == NULL ||
      !policy_shape_valid (policy))
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_ARGUMENT,
                           "target material path or policy is invalid");
      goto out;
    }
  manifest = read_exact_protected (manifest_path, policy->manifest_length,
                                   FALSE, policy, audit, &manifest_length,
                                   error);
  if (manifest == NULL)
    goto out;
  material = g_new0 (GoodixTargetMaterial, 1);
  material->policy = *policy;
  material->audit = audit;
  if (policy->manifest_length != 0u ?
      (!digest (manifest, manifest_length, actual) ||
       CRYPTO_memcmp (actual, policy->manifest_sha256, 32u) != 0) :
      !parse_manifest (manifest, manifest_length, &material->policy))
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_CONTENT,
                           "target manifest schema or field rejected");
      goto out;
    }
  g_clear_pointer (&manifest, g_free);

  transport = read_exact_protected (transport_path, policy->transport_length,
                                    TRUE, policy, audit, NULL, error);
  if (transport == NULL)
    goto out;
  if (memcmp (transport, "G5125POC", 8) != 0 ||
      transport[8] != 1u || transport[9] != 0u ||
      transport[10] != 24u || transport[11] != 0u ||
      transport[12] != 0xc6u || transport[13] != 0x27u ||
      transport[14] != 0x25u || transport[15] != 0x51u ||
      transport[16] != 1u || transport[17] != 0u ||
      transport[18] != 32u || transport[19] != 0u ||
      transport[20] != 32u || transport[21] != 0u ||
      transport[22] != 0u || transport[23] != 0u)
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_CONTENT,
                           "transport material magic mismatch");
      goto out;
    }
  if (!digest (transport, policy->transport_length, actual) ||
      CRYPTO_memcmp (actual, material->policy.transport_sha256, 32) != 0)
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_CONTENT,
                           "transport material SHA-256 mismatch");
      goto out;
    }
  material->psk = g_memdup2 (transport + 24, GOODIX_SECURE_SESSION_PSK_LENGTH);
  memcpy (material->transport_validator, transport + 56u, 32u);
  OPENSSL_cleanse (transport, policy->transport_length);
  observe_cleansed (policy, "psk-scratch", transport,
                    policy->transport_length);
  if (audit != NULL)
    {
      audit->psk_scratch_cleanse_count++;
      audit->psk_scratch_cleansed = TRUE;
    }
  g_clear_pointer (&transport, g_free);

  config = read_exact_protected (config90_path, policy->config90_length,
                                 FALSE, policy, audit, NULL, error);
  if (config == NULL)
    goto out;
  if (!digest (config, policy->config90_length, actual) ||
      CRYPTO_memcmp (actual, material->policy.config90_sha256, 32) != 0)
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_CONTENT,
                           "CONFIG90 SHA-256 mismatch");
      goto out;
    }
  if (!config_finalizer_valid (config, policy))
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_CONTENT,
                           "CONFIG90 finalizer mismatch");
      goto out;
    }
  if (policy->manifest_length == 0u)
    for (guint i = 0; i < 4u; i++)
      memcpy (material->policy.dac_values[i],
              config + material->policy.dac_offsets[i] + 2u, 2u);
  if (!config_correlations_valid (config, &material->policy))
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_CONTENT,
                           "CONFIG90 DAC correlation mismatch");
      goto out;
    }
  material->config90 = config;
  config = NULL;
  OPENSSL_cleanse (actual, sizeof actual);
  return material;

out:
  g_clear_pointer (&manifest, g_free);
  if (transport != NULL)
    {
      OPENSSL_cleanse (transport, policy != NULL ? policy->transport_length : 0);
      if (policy != NULL)
        observe_cleansed (policy, "psk-scratch", transport,
                          policy->transport_length);
      if (audit != NULL)
        {
          audit->psk_scratch_cleanse_count++;
          audit->psk_scratch_cleansed = TRUE;
        }
      g_free (transport);
    }
  if (config != NULL)
    {
      OPENSSL_cleanse (config, policy->config90_length);
      g_free (config);
      config = NULL;
    }
  goodix_target_material_free (material);
  OPENSSL_cleanse (actual, sizeof actual);
  return NULL;
}

gboolean
goodix_target_material_bind (GoodixTargetMaterial *material,
                             const guint8          seed_a[6],
                             const guint8          seed_b[6],
                             GError              **error)
{
  guint8 validator[32] = { 0 };
  guint8 actual[32] = { 0 };
  gboolean ok = FALSE;

  if (material == NULL || material->bound || material->psk == NULL ||
      seed_a == NULL || seed_b == NULL)
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_STATE,
                           "target material cannot be bound in current state");
      goto out;
    }
  if (material->audit != NULL)
    material->audit->bind_count++;
  if (!goodix_d190_bind_validator (material->psk, 32, seed_a, 6, seed_b, 6,
                                   validator, error))
    goto out;
  if (!digest (validator, sizeof validator, actual) ||
      CRYPTO_memcmp (validator, material->transport_validator, 32u) != 0 ||
      ((material->policy.e4_validator_sha256[0] != 0u) &&
       CRYPTO_memcmp (actual, material->policy.e4_validator_sha256, 32u) != 0))
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_BINDING,
                           "derived E4 validator digest failed");
      goto out;
    }
  memcpy (material->policy.e4_validator_sha256, actual, sizeof actual);
  material->validator = g_memdup2 (validator, sizeof validator);
  OPENSSL_cleanse (material->transport_validator,
                   sizeof material->transport_validator);
  material->bound = TRUE;
  if (material->audit != NULL)
    material->audit->e4_binding_match = TRUE;
  ok = TRUE;
out:
  OPENSSL_cleanse (validator, sizeof validator);
  OPENSSL_cleanse (actual, sizeof actual);
  return ok;
}

gboolean
goodix_target_material_get_fdt_hashes (GoodixTargetMaterial *material,
                                       guint8 cache_sha256[32],
                                       guint8 otp_sha256[32],
                                       GError **error)
{
  if (material == NULL || cache_sha256 == NULL || otp_sha256 == NULL)
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_STATE,
                           "target manifest hashes are unavailable");
      return FALSE;
    }
  memcpy (cache_sha256, material->policy.fdt_cache_sha256, 32u);
  memcpy (otp_sha256, material->policy.otp_a6_response_sha256, 32u);
  return TRUE;
}

gboolean
goodix_target_material_get_secure_session_material (
  GoodixTargetMaterial        *material,
  GoodixSecureSessionMaterial *view,
  GError                     **error)
{
  if (material == NULL || view == NULL || !material->bound ||
      material->validator == NULL || material->psk == NULL ||
      material->config90 == NULL)
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_STATE,
                           "target material is not completely bound");
      return FALSE;
    }
  memset (view, 0, sizeof *view);
  view->expected_identity = app12509_identity;
  view->expected_identity_length = sizeof app12509_identity;
  view->e4_validator = material->validator;
  view->e4_validator_length = 32;
  memcpy (view->e4_validator_sha256,
          material->policy.e4_validator_sha256, 32);
  memcpy (view->a2_response_sha256,
          material->policy.a2_response_sha256, 32);
  memcpy (view->chip82_response_sha256,
          material->policy.chip82_response_sha256, 32);
  memcpy (view->otp_a6_response_sha256,
          material->policy.otp_a6_response_sha256, 32);
  memcpy (view->dac_values, material->policy.dac_values,
          sizeof view->dac_values);
  view->config90 = material->config90;
  view->config90_length = material->policy.config90_length;
  memcpy (view->config90_sha256, material->policy.config90_sha256, 32);
  view->psk = material->psk;
  view->psk_length = 32;
  return TRUE;
}

void
goodix_target_material_free (GoodixTargetMaterial *material)
{
  if (material == NULL)
    return;
  if (material->audit != NULL)
    material->audit->owner_free_count++;
  if (material->psk != NULL)
    {
      cleanse_free (&material->policy, "owner-psk", material->psk, 32);
      if (material->audit != NULL)
        material->audit->owner_psk_cleanse_count++;
    }
  if (material->validator != NULL)
    {
      cleanse_free (&material->policy, "e4-validator", material->validator, 32);
      if (material->audit != NULL)
        material->audit->validator_cleanse_count++;
    }
  if (material->config90 != NULL)
    {
      cleanse_free (&material->policy, "config90", material->config90,
                    GOODIX_SECURE_SESSION_CONFIG90_LENGTH);
      if (material->audit != NULL)
        material->audit->config90_cleanse_count++;
    }
  if (material->audit != NULL)
    material->audit->project_secret_zeroized = TRUE;
  OPENSSL_cleanse (material, sizeof *material);
  g_free (material);
}
