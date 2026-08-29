/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_target_material.h"
#include <errno.h>
#include <fcntl.h>
#include <openssl/crypto.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

struct _GoodixTargetMaterial { GoodixSecureSessionMaterial session; guint8 psk[32], validator[32], config[224]; };
static const guint8 identity[]="GF_ST411SEC_APP_12509";
static const guint8 a2_pin[32]={0x39,0xe4,0x69,0xce,0x5a,0x5b,0xa3,0x13,0x6c,0x4a,0x44,0x38,0x1f,0x2e,0x41,0x83,0xdc,0xa2,0x75,0x25,0x7a,0xdf,0xc3,0xf0,0x02,0x50,0x94,0xf0,0x5c,0x02,0x2f,0x5f};
static const guint8 p82[32]={0x82,0x53,0x7d,0x2c,0x10,0x88,0x87,0xba,0xef,0x12,0x8b,0x47,0xad,0x40,0x1f,0xc8,0x88,0xd5,0x4b,0x18,0x46,0x73,0xb1,0xfc,0x23,0x81,0x1d,0x79,0xab,0x6d,0x57,0x03};
static const guint8 pa6[32]={0xd7,0xe8,0x1a,0x41,0x5a,0xa5,0xe7,0xb0,0x16,0x8c,0x9a,0x63,0x27,0x56,0xd1,0xdc,0x8b,0x7b,0x47,0x34,0x6c,0xc0,0xa4,0x4d,0xc6,0x87,0x96,0xf8,0x54,0xc2,0xb9,0x2b};
static GQuark q(void){return g_quark_from_static_string("goodix-target-material-error");}
static gboolean hex(const gchar*s,guint8*out){for(guint i=0;i<32;i++){gint a=g_ascii_xdigit_value(s[2*i]),b=g_ascii_xdigit_value(s[2*i+1]);if(a<0||b<0)return FALSE;out[i]=(guint8)((a<<4)|b);}return TRUE;}
void goodix_target_material_policy_production(GoodixTargetMaterialPolicy*p){memset(p,0,sizeof*p);p->required_uid=0;p->required_mode=0600;hex("1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15",p->manifest_sha256);hex("eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75",p->transport_sha256);hex("e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82",p->config_sha256);hex("1fa642d3f190e7074d1db201aa32ee8f34e41d69d55797158b9480affb3d0b87",p->validator_sha256);}
static gboolean digest(const guint8*d,gsize n,const guint8 want[32]){g_autoptr(GChecksum)c=g_checksum_new(G_CHECKSUM_SHA256);guint8 got[32];gsize l=32;g_checksum_update(c,d,(gssize)n);g_checksum_get_digest(c,got,&l);return l==32&&CRYPTO_memcmp(got,want,32)==0;}
static gboolean config_contract(const guint8*c){static const guint8 tuples[4][4]={{0x20,0x02,0xd8,0x0b},{0x36,0x02,0xbe,0},{0x38,0x02,0xbd,0},{0x3a,0x02,0xbc,0}};static const guint off[4]={117,121,125,129};guint32 sum=0;for(guint i=0;i<111;i++)sum+=(guint16)(c[2*i]|((guint16)c[2*i+1]<<8));if((guint16)(0u-0xa5a5u-sum)!=(guint16)(c[222]|((guint16)c[223]<<8)))return FALSE;for(guint i=0;i<4;i++)if(memcmp(c+off[i],tuples[i],4)!=0)return FALSE;return TRUE;}
static GBytes *read_protected(const gchar*path,const GoodixTargetMaterialPolicy*p,GError**e){int flags=O_RDONLY;
#ifdef O_CLOEXEC
flags|=O_CLOEXEC;
#endif
#ifdef O_NOFOLLOW
flags|=O_NOFOLLOW;
#endif
int fd=open(path,flags);struct stat st;guint8 buf[4096];GByteArray*a=NULL;if(fd<0){g_set_error(e,q(),1,"protected input open failed: %s",g_strerror(errno));return NULL;}if(fstat(fd,&st)<0||!S_ISREG(st.st_mode)||st.st_uid!=p->required_uid||(st.st_mode&07777)!=p->required_mode){g_set_error_literal(e,q(),2,"protected input metadata rejected");close(fd);return NULL;}a=g_byte_array_new();for(;;){ssize_t n=read(fd,buf,sizeof buf);if(n<0){g_set_error_literal(e,q(),3,"protected input read failed");g_byte_array_unref(a);close(fd);return NULL;}if(n==0)break;g_byte_array_append(a,buf,(guint)n);}struct stat after;if(fstat(fd,&after)<0||after.st_dev!=st.st_dev||after.st_ino!=st.st_ino||after.st_uid!=st.st_uid||after.st_mode!=st.st_mode||after.st_size!=st.st_size){g_set_error_literal(e,q(),4,"protected input changed during read");g_byte_array_unref(a);close(fd);return NULL;}close(fd);return g_byte_array_free_to_bytes(a);}
GoodixTargetMaterial *goodix_target_material_load(const gchar*m,const gchar*t,const gchar*c,const guint8 sa[6],const guint8 sb[6],const GoodixTargetMaterialPolicy*p,GError**e){g_autoptr(GBytes)mb=read_protected(m,p,e),tb=NULL,cb=NULL;GoodixTargetMaterial*o=NULL;gsize ml,tl,cl;const guint8 *md,*td,*cd;if(!mb)return NULL;tb=read_protected(t,p,e);if(!tb)return NULL;cb=read_protected(c,p,e);if(!cb)return NULL;md=g_bytes_get_data(mb,&ml);td=g_bytes_get_data(tb,&tl);cd=g_bytes_get_data(cb,&cl);if(!digest(md,ml,p->manifest_sha256)||tl!=88||memcmp(td,"G5125POC",8)!=0||!digest(td,tl,p->transport_sha256)||cl!=224||!digest(cd,cl,p->config_sha256)||!config_contract(cd)){g_set_error_literal(e,q(),5,"protected input content pin or correlation rejected");return NULL;}o=g_new0(GoodixTargetMaterial,1);memcpy(o->psk,td+24,32);memcpy(o->config,cd,224);if(!goodix_d190_bind_validator(o->psk,sa,sb,o->validator,e)||!digest(o->validator,32,p->validator_sha256)){if(e&&*e==NULL)g_set_error_literal(e,q(),6,"derived E4 pin rejected");goodix_target_material_free(o);return NULL;}o->session.expected_identity=identity;o->session.expected_identity_length=sizeof identity;o->session.e4_validator=o->validator;o->session.e4_validator_length=32;memcpy(o->session.e4_validator_sha256,p->validator_sha256,32);memcpy(o->session.a2_response_sha256,a2_pin,32);memcpy(o->session.chip82_response_sha256,p82,32);memcpy(o->session.otp_a6_response_sha256,pa6,32);o->session.dac_values[0][0]=0xd8;o->session.dac_values[0][1]=0x0b;o->session.dac_values[1][0]=0xbe;o->session.dac_values[2][0]=0xbd;o->session.dac_values[3][0]=0xbc;o->session.config90=o->config;o->session.config90_length=224;memcpy(o->session.config90_sha256,p->config_sha256,32);o->session.psk=o->psk;o->session.psk_length=32;return o;}
const GoodixSecureSessionMaterial *goodix_target_material_session(GoodixTargetMaterial*o){return o?&o->session:NULL;}
void goodix_target_material_free(GoodixTargetMaterial*o){if(!o)return;goodix_d190_clear(o->psk,32);goodix_d190_clear(o->validator,32);goodix_d190_clear(o->config,224);goodix_d190_clear(o,sizeof*o);g_free(o);}
