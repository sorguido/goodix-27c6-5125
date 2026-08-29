/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Adapted from the project-authored BSD-2-Clause D190 reference identified in
 * docs/LICENSING_AND_PROVENANCE.md.  This deliberately exposes only the
 * reusable secret+seed binder, not the historical Python runtime/PE parser. */
#include "goodix_d190_binder.h"
#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/hmac.h>
#include <string.h>

static GQuark error_quark (void) { return g_quark_from_static_string ("goodix-d190-error"); }
void goodix_d190_clear (gpointer p, gsize n) { if (p != NULL && n != 0) OPENSSL_cleanse (p, n); }

static gboolean
sha256 (const guint8 *p, gsize n, guint8 out[32])
{
  unsigned int l = 0;
  return EVP_Digest (p, n, out, &l, EVP_sha256 (), NULL) == 1 && l == 32;
}

static gboolean
aes_block (const guint8 *key, guint key_len, const guint8 in[16], guint8 out[16], gboolean decrypt)
{
  EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new ();
  const EVP_CIPHER *cipher = key_len == 16 ? EVP_aes_128_ecb () : key_len == 24 ? EVP_aes_192_ecb () : EVP_aes_256_ecb ();
  gint a = 0, b = 0;
  gboolean ok = ctx != NULL && EVP_CipherInit_ex (ctx, cipher, NULL, key, NULL, decrypt ? 0 : 1) == 1 &&
                EVP_CIPHER_CTX_set_padding (ctx, 0) == 1 && EVP_CipherUpdate (ctx, out, &a, in, 16) == 1 &&
                EVP_CipherFinal_ex (ctx, out + a, &b) == 1 && a + b == 16;
  EVP_CIPHER_CTX_free (ctx);
  return ok;
}

static guint32 crc32_oem (const guint8 *p, gsize n)
{
  guint32 v = G_MAXUINT32;
  for (gsize i = 0; i < n; i++) { v ^= (guint32) p[i] << 24; for (guint j = 0; j < 8; j++) v = (v << 1) ^ ((v & 0x80000000u) ? 0x04c11db7u : 0); }
  return v;
}

static gboolean
half (const guint8 seed[6], guint8 out[16])
{
  guint8 expanded[24], digest[32], block[16], transformed[16], hkey[16] = "123456", h[32];
  unsigned int hl = 0;
  gboolean ok = FALSE;
  for (guint r = 0; r < 4; r++) for (guint i = 0; i < 6; i++) expanded[r * 6 + i] = (guint8) ((seed[i] >> (2*r+1)) | (seed[i] << (8-(2*r+1))));
  if (!sha256 (expanded, 3, digest)) goto done;
  memcpy (out, digest, 2);
  for (guint i = 0; i < 4; i++) {
    guint8 key[32] = { 0 }; guint kl = i == 0 ? 16u : i == 1 ? 16u : i == 2 ? 32u : 24u;
    memcpy (block, expanded + (i + 1) * 3, 3); memset (block + 3, 0xcc, 13);
    if (!aes_block (key, kl, block, transformed, i % 2 == 0)) { goodix_d190_clear (key, sizeof key); goto done; }
    memcpy (out + 2 + 2*i, transformed, 2); goodix_d190_clear (key, sizeof key);
  }
  if (HMAC (EVP_sha256 (), hkey, sizeof hkey, expanded + 15, 3, h, &hl) == NULL || hl != 32) goto done;
  memcpy (out + 10, h, 2);
  { guint32 c = crc32_oem (expanded + 18, 3); out[12]=(guint8)(c>>24); out[13]=(guint8)(c>>16); }
  if (!sha256 (expanded + 21, 3, digest)) goto done;
  memcpy (out + 14, digest, 2); ok = TRUE;
done:
  goodix_d190_clear (expanded, sizeof expanded); goodix_d190_clear (digest, sizeof digest);
  goodix_d190_clear (block, sizeof block); goodix_d190_clear (transformed, sizeof transformed); goodix_d190_clear (h, sizeof h);
  return ok;
}

gboolean
goodix_d190_bind_validator (const guint8 secret[32], const guint8 seed_a[6], const guint8 seed_b[6], guint8 validator[32], GError **error)
{
  static const guint8 fixed_aad[16] = {0x52,0x2d,0xc1,0xf0,0x99,0x56,0x7d,0x07,0xf4,0x7f,0x37,0xa3,0x2a,0x84,0x42,0x7d};
  static const guint8 label[] = "kgoodwixg\0kaelrgnoerlithm";
  guint8 ha[16], hb[16], key[32], fixed[sizeof label - 1 + 4], msg[4 + sizeof fixed], t1[32], t2[32], derived[48];
  guint8 header[6] = {2,255,32,0,0,0}, inner_input[78], nonce[32], ciphertext[32], tag[16], outer_input[54], envelope[102], mac[32];
  unsigned int l = 0; EVP_CIPHER_CTX *ctx = NULL; gint n = 0, total = 0; gboolean ok = FALSE;
  if (secret == NULL || seed_a == NULL || seed_b == NULL || validator == NULL) { g_set_error_literal (error,error_quark(),1,"D190 arguments are invalid"); return FALSE; }
  if (!half(seed_a,ha) || !half(seed_b,hb)) goto crypto_fail;
  memcpy(key,ha,16); memcpy(key+16,hb,16); memcpy(fixed,label,sizeof label-1); fixed[sizeof fixed-4]=0; fixed[sizeof fixed-3]=0; fixed[sizeof fixed-2]=1; fixed[sizeof fixed-1]=0x80;
  memcpy(msg+4,fixed,sizeof fixed);
  for (guint counter=1; counter<=2; counter++) { msg[0]=0;msg[1]=0;msg[2]=0;msg[3]=(guint8)counter; if (HMAC(EVP_sha256(),key,32,msg,sizeof msg,counter==1?t1:t2,&l)==NULL||l!=32) goto crypto_fail; }
  memcpy(derived,t1,32); memcpy(derived+32,t2,16);
  memcpy(inner_input,header,6); memcpy(inner_input+6,secret,8); for(guint i=0;i<16;i++){inner_input[14+4*i]=3;inner_input[15+4*i]=0;inner_input[16+4*i]=0;inner_input[17+4*i]=0;}
  if(!sha256(inner_input,sizeof inner_input,nonce)) goto crypto_fail;
  ctx=EVP_CIPHER_CTX_new(); if(ctx==NULL||EVP_EncryptInit_ex(ctx,EVP_aes_256_gcm(),NULL,NULL,NULL)!=1||EVP_CIPHER_CTX_ctrl(ctx,EVP_CTRL_GCM_SET_IVLEN,16,NULL)!=1||EVP_EncryptInit_ex(ctx,NULL,NULL,derived,nonce)!=1||EVP_EncryptUpdate(ctx,NULL,&n,fixed_aad,16)!=1||EVP_EncryptUpdate(ctx,ciphertext,&n,secret,32)!=1) goto crypto_fail; total=n;
  if(EVP_EncryptFinal_ex(ctx,ciphertext+total,&n)!=1||EVP_CIPHER_CTX_ctrl(ctx,EVP_CTRL_GCM_GET_TAG,16,tag)!=1) goto crypto_fail;
  memcpy(envelope+32,header,6); memcpy(envelope+38,nonce,16); memcpy(envelope+54,ciphertext,32); memcpy(envelope+86,tag,16);
  memcpy(outer_input,header,6); memcpy(outer_input+6,ciphertext,32); memcpy(outer_input+38,tag,16);
  if(HMAC(EVP_sha256(),derived+16,32,outer_input,sizeof outer_input,mac,&l)==NULL||l!=32) goto crypto_fail;
  memcpy(envelope,mac,32);
  if(!sha256(envelope,sizeof envelope,validator)) goto crypto_fail;
  ok=TRUE;
  goto done;
crypto_fail: g_set_error_literal(error,error_quark(),2,"D190 cryptographic binding failed");
done: EVP_CIPHER_CTX_free(ctx); goodix_d190_clear(ha,sizeof ha);goodix_d190_clear(hb,sizeof hb);goodix_d190_clear(key,sizeof key);goodix_d190_clear(t1,sizeof t1);goodix_d190_clear(t2,sizeof t2);goodix_d190_clear(derived,sizeof derived);goodix_d190_clear(inner_input,sizeof inner_input);goodix_d190_clear(nonce,sizeof nonce);goodix_d190_clear(ciphertext,sizeof ciphertext);goodix_d190_clear(tag,sizeof tag);goodix_d190_clear(outer_input,sizeof outer_input);goodix_d190_clear(envelope,sizeof envelope);goodix_d190_clear(mac,sizeof mac); if(!ok) goodix_d190_clear(validator,32); return ok;
}
