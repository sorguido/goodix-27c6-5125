/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "goodix_target_material.h"

#include "goodix_d190_binder.h"

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
  static const guint8 manifest_hash[32] = {
    0x1b,0x5c,0x38,0x91,0xc9,0x9b,0x4e,0xe7,
    0x1d,0x37,0xa6,0x99,0x42,0xe0,0x8d,0xcf,
    0x9d,0x39,0x85,0x74,0x09,0x58,0x68,0x7a,
    0xc4,0xb0,0xd6,0xeb,0x7c,0xcd,0xcf,0x15
  };
  static const guint8 transport_hash[32] = {
    0xeb,0x47,0xbb,0xed,0x40,0xe0,0x79,0xca,
    0x78,0x0c,0xd9,0xcd,0x4b,0x23,0x24,0x52,
    0x0a,0x67,0x58,0x4a,0xd3,0xd5,0x76,0x67,
    0x49,0x14,0x15,0x2f,0xd6,0x08,0x0a,0x75
  };
  static const guint8 config_hash[32] = {
    0xe1,0x98,0x8b,0x11,0x15,0xad,0xe7,0x48,
    0xf6,0xcf,0x5d,0xca,0x8d,0x31,0xaa,0xdf,
    0x99,0x87,0x1a,0x78,0x65,0xb9,0x7d,0x7e,
    0xc0,0x97,0x1d,0x0d,0xa2,0x1d,0x4d,0x82
  };
  static const guint8 e4_hash[32] = {
    0x1f,0xa6,0x42,0xd3,0xf1,0x90,0xe7,0x07,
    0x4d,0x1d,0xb2,0x01,0xaa,0x32,0xee,0x8f,
    0x34,0xe4,0x1d,0x69,0xd5,0x57,0x97,0x15,
    0x8b,0x94,0x80,0xaf,0xfb,0x3d,0x0b,0x87
  };
  static const guint8 a2_hash[32] = {
    0x39,0xe4,0x69,0xce,0x5a,0x5b,0xa3,0x13,
    0x6c,0x4a,0x44,0x38,0x1f,0x2e,0x41,0x83,
    0xdc,0xa2,0x75,0x25,0x7a,0xdf,0xcf,0x3c,
    0x00,0x25,0x09,0x4f,0x05,0xc0,0x22,0xf5
  };
  static const guint8 chip_hash[32] = {
    0x82,0x53,0x7d,0x2c,0x10,0x88,0x87,0xba,
    0xef,0x12,0x8b,0x47,0xad,0x40,0x1f,0xc8,
    0x88,0xd5,0x4b,0x18,0x46,0x73,0xb1,0xfc,
    0x23,0x81,0x1d,0x79,0xab,0x6d,0x57,0x03
  };
  static const guint8 otp_hash[32] = {
    0xd7,0xe8,0x1a,0x41,0x5a,0xa5,0xe7,0xb0,
    0x16,0x8c,0x9a,0x63,0x27,0x56,0xd1,0xdc,
    0x8b,0x7b,0x47,0x34,0x6c,0xc0,0xa4,0x4d,
    0xc6,0x87,0x96,0xf8,0x54,0xc2,0xb9,0x2b
  };
  static const guint16 registers[4] = { 0x0220, 0x0236, 0x0238, 0x023a };
  static const guint8 values[4][2] = {
    { 0xd8, 0x0b }, { 0xbe, 0x00 }, { 0xbd, 0x00 }, { 0xbc, 0x00 }
  };
  static const guint offsets[4] = { 117, 121, 125, 129 };

  g_return_if_fail (policy != NULL);
  memset (policy, 0, sizeof *policy);
  policy->owner_uid = 0;
  policy->owner_gid = 0;
  policy->mode = 0600;
  policy->manifest_length = GOODIX_TARGET_MANIFEST_LENGTH;
  policy->transport_length = GOODIX_TARGET_TRANSPORT_LENGTH;
  policy->config90_length = GOODIX_SECURE_SESSION_CONFIG90_LENGTH;
  memcpy (policy->manifest_sha256, manifest_hash, 32);
  memcpy (policy->transport_sha256, transport_hash, 32);
  memcpy (policy->config90_sha256, config_hash, 32);
  policy->config90_finalizer[0] = 0x51;
  policy->config90_finalizer[1] = 0x9a;
  memcpy (policy->e4_validator_sha256, e4_hash, 32);
  memcpy (policy->a2_response_sha256, a2_hash, 32);
  memcpy (policy->chip82_response_sha256, chip_hash, 32);
  memcpy (policy->otp_a6_response_sha256, otp_hash, 32);
  memcpy (policy->dac_registers, registers, sizeof registers);
  memcpy (policy->dac_values, values, sizeof values);
  memcpy (policy->dac_offsets, offsets, sizeof offsets);
}

static gboolean
policy_shape_valid (const GoodixTargetMaterialPolicy *policy)
{
  static const guint16 registers[4] = { 0x0220, 0x0236, 0x0238, 0x023a };
  static const guint offsets[4] = { 117, 121, 125, 129 };

  return policy != NULL && policy->mode == 0600 &&
         policy->manifest_length > 0 && policy->manifest_length <= 16384 &&
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
         status->st_size >= 0 && (guint64) status->st_size == expected_length;
}

static guint8 *
read_exact_protected (const gchar                      *path,
                      gsize                             expected_length,
                      gboolean                          sensitive,
                      const GoodixTargetMaterialPolicy *policy,
                      GoodixTargetMaterialAudit        *audit,
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
  buffer = g_malloc0 (expected_length);
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
         CRYPTO_memcmp (config + 222, policy->config90_finalizer, 2) == 0;
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
                                   FALSE, policy, audit, error);
  if (manifest == NULL)
    goto out;
  if (!digest (manifest, policy->manifest_length, actual) ||
      CRYPTO_memcmp (actual, policy->manifest_sha256, 32) != 0)
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_CONTENT,
                           "target manifest SHA-256 mismatch");
      goto out;
    }
  g_clear_pointer (&manifest, g_free);

  transport = read_exact_protected (transport_path, policy->transport_length,
                                    TRUE, policy, audit, error);
  if (transport == NULL)
    goto out;
  if (memcmp (transport, "G5125POC", 8) != 0)
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_CONTENT,
                           "transport material magic mismatch");
      goto out;
    }
  if (!digest (transport, policy->transport_length, actual) ||
      CRYPTO_memcmp (actual, policy->transport_sha256, 32) != 0)
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_CONTENT,
                           "transport material SHA-256 mismatch");
      goto out;
    }
  material = g_new0 (GoodixTargetMaterial, 1);
  material->policy = *policy;
  material->audit = audit;
  material->psk = g_memdup2 (transport + 24, GOODIX_SECURE_SESSION_PSK_LENGTH);
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
                                 FALSE, policy, audit, error);
  if (config == NULL)
    goto out;
  if (!digest (config, policy->config90_length, actual) ||
      CRYPTO_memcmp (actual, policy->config90_sha256, 32) != 0)
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
  if (!config_correlations_valid (config, policy))
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
      CRYPTO_memcmp (actual, material->policy.e4_validator_sha256, 32) != 0)
    {
      g_set_error_literal (error, GOODIX_TARGET_MATERIAL_ERROR,
                           GOODIX_TARGET_MATERIAL_ERROR_BINDING,
                           "derived E4 validator target pin mismatch");
      goto out;
    }
  material->validator = g_memdup2 (validator, sizeof validator);
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
