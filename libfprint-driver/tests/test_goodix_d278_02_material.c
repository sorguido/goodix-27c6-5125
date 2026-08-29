/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "goodix_d190_binder.h"
#include "goodix_d190_pe.h"
#include <glib.h>
#include <glib/gstdio.h>
#include <unistd.h>
static const guint8 secrets[5][32]={{0},{[0 ... 31]=1},{0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31},{0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55},{0x31,0xdc,0x31,0x42,0x96,0x63,0x1f,0xa5,0x2d,0xb5,0xa0,0x9e,0x62,0x5f,0x74,0xd4,0x3f,0x54,0x20,0x45,0x5a,0x21,0x42,0x72,0xab,0x44,0x4f,0x84,0x39,0x3e,0x8d,0x5a}};
static const gchar*expected[5]={"b5e0beeb94c84eb99b883abd5c251073c56b91035c562a91a46c7f3349c36c89","e51d069d67065a052307d3bd6dd8edf377e8b2389dc309475891e415e5f2148c","d1ba9a4790f8d47ba8b50043d72b577cdc2d1b701d466197aa741a94fd0f1ec4","ea43b0f9a2eae84d55fa9b0a961c35b7dd8e5c2594e5e4562c92c3f198a19209","af13a21ec8f8250b47da268f32ef74cd0ff5dbc0f8b48b93ee5411e422e8a9b4"};
static void kat(gconstpointer data){guint i=GPOINTER_TO_UINT(data);guint8 a[6],b[6],out[32];g_autoptr(GError)e=NULL;const gchar*pe=g_getenv("GOODIX_CANONICAL_PE");g_assert_nonnull(pe);g_assert_true(goodix_d190_extract_seeds(pe,a,b,&e));g_assert_true(goodix_d190_bind_validator(secrets[i],a,b,out,&e));/* expected values are independent OEM-oracle validators */gchar hex[65];for(guint j=0;j<32;j++)g_snprintf(hex+2*j,3,"%02x",out[j]);g_assert_cmpstr(hex,==,expected[i]);goodix_d190_clear(a,6);goodix_d190_clear(b,6);goodix_d190_clear(out,32);}
static void wrong_pe(void){guint8 a[6]={0},b[6]={0};g_autoptr(GError)e=NULL;g_autofree gchar*p=NULL;gint fd=g_file_open_tmp("d278-bad-XXXXXX",&p,&e);g_assert_cmpint(fd,>=,0);g_assert_cmpint(write(fd,"MZ",2),==,2);close(fd);g_assert_false(goodix_d190_extract_seeds(p,a,b,&e));g_assert_nonnull(e);g_unlink(p);}
int main(int argc,char**argv){g_test_init(&argc,&argv,NULL);for(guint i=0;i<5;i++)g_test_add_data_func(g_strdup_printf("/d278_02/binder/kat_%u",i),GUINT_TO_POINTER(i),kat);g_test_add_func("/d278_02/pe/wrong_hash",wrong_pe);return g_test_run();}
