/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Tool-only bounded parser adapted from the project-authored BSD D190 parser;
 * the PE is hash-gated and read as inert bytes, never loaded or executed. */
#include "goodix_d190_pe.h"
#include "goodix_d190_binder.h"
#include <openssl/crypto.h>
#include <string.h>
static GQuark q(void){return g_quark_from_static_string("goodix-d190-pe-error");}
static guint16 le16(const guint8*p){return(guint16)(p[0]|((guint16)p[1]<<8));}static guint32 le32(const guint8*p){return(guint32)(p[0]|((guint32)p[1]<<8)|((guint32)p[2]<<16)|((guint32)p[3]<<24));}
static gboolean hash_ok(const guint8*d,gsize n){static const gchar want[]="904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2";g_autoptr(GChecksum)c=g_checksum_new(G_CHECKSUM_SHA256);g_checksum_update(c,d,(gssize)n);return g_str_equal(g_checksum_get_string(c),want);}
static const guint8 *rva(const guint8*d,gsize n,guint32 pe,guint32 value,gsize need){guint count=le16(d+pe+6),optional=le16(d+pe+20);gsize table=pe+24u+optional;if(count==0||count>96||table>n||count>(n-table)/40)return NULL;for(guint i=0;i<count;i++){const guint8*s=d+table+40*i;guint32 vs=le32(s+8),va=le32(s+12),rs=le32(s+16),ro=le32(s+20),back=MIN(vs,rs);if(value>=va&&need<=back&&value-va<=back-need&&ro<=n&&value-va<=n-ro&&need<=n-ro-(value-va))return d+ro+value-va;}return NULL;}
gboolean goodix_d190_extract_seeds(const gchar*path,guint8 a[6],guint8 b[6],GError**e){g_autofree gchar*raw=NULL;gsize n=0;const guint8*d,*x,*y;guint32 pe;guint matches=0;if(!g_file_get_contents(path,&raw,&n,e))return FALSE;d=(const guint8*)raw;if(!hash_ok(d,n)){g_set_error_literal(e,q(),1,"canonical PE hash mismatch");return FALSE;}if(n<64||memcmp(d,"MZ",2)!=0||(pe=le32(d+0x3c))>n-24||memcmp(d+pe,"PE\0\0",4)!=0){g_set_error_literal(e,q(),2,"bounded PE header rejected");return FALSE;}x=rva(d,n,pe,0x56f030,6);y=rva(d,n,pe,0x69d0,14);if(!x||!y||memcmp(y,"\xc7\x45\x9f",3)||memcmp(y+7,"\xc7\x45\xa3",3)){g_set_error_literal(e,q(),3,"producer locations rejected");return FALSE;}for(gsize i=0;i+12<=n;i++)if(memcmp(d+i,y,12)==0)matches++;if(matches!=1){g_set_error_literal(e,q(),4,"producer instruction is not unique");return FALSE;}memcpy(a,x,6);memcpy(b,y+3,4);memcpy(b+4,y+10,2);return TRUE;}
