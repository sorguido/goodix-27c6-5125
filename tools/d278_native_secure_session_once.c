/* SPDX-License-Identifier: GPL-2.0-or-later */
/* D278/02 test-only entrypoint.  Material is always closed before any future
 * USB seam.  This program is not installed or registered as a libfprint
 * device. */
#include "goodix_d190_binder.h"
#include "goodix_d190_pe.h"
#include "goodix_target_material.h"
#include <glib.h>
#include <stdio.h>
#include <string.h>
static const guint phase_timeout_ms[]={1000,1000,1000,500,750,1000,500,250,250,250,250,1000,1000,3000};
static void status(const gchar*result,const gchar*failure){printf("{\"result\":\"%s\",\"failure_class\":\"%s\",\"current_live_authorized\":false,\"usb_open_attempt_count\":0,\"usb_open_count\":0,\"usb_claim_count\":0,\"real_usb_submit_count\":0,\"command_count\":0,\"retry_count\":0,\"transport_reopen_count\":0,\"device_reset_count\":0,\"persistent_device_write_count\":0,\"d4_reachable\":false,\"application_data_count\":0,\"terminal_cleanup_completed\":true}\n",result,failure);}
int main(int argc,char**argv){guint8 a[6]={0},b[6]={0};g_autoptr(GError)e=NULL;GoodixTargetMaterial*owner=NULL;GoodixTargetMaterialPolicy policy;if(argc!=2){g_printerr("usage: %s --self-test|--material-preflight-only|--live-exact-secure-session\n",argv[0]);return 2;}if(g_str_equal(argv[1],"--self-test")){guint sum=0;for(guint i=0;i<G_N_ELEMENTS(phase_timeout_ms);i++)sum+=phase_timeout_ms[i];if(sum!=11750){status("FAIL","WATCHDOG_CONTRACT");return 1;}status("PASS","NONE");return 0;}if(!goodix_d190_extract_seeds("analysis/D230/work/GoodixExport/gfusb.dll",a,b,&e)){status("FAIL","PRODUCER_MATERIAL");return 1;}goodix_target_material_policy_production(&policy);owner=goodix_target_material_load("/var/lib/goodix-5125-poc/target-material-manifest.json","/var/lib/goodix-5125-poc/transport-material.bin","/var/lib/goodix-5125-poc/target-config-90.bin",a,b,&policy,&e);goodix_d190_clear(a,6);goodix_d190_clear(b,6);if(!owner){status("FAIL","PROTECTED_MATERIAL");return 1;}if(g_str_equal(argv[1],"--material-preflight-only")){goodix_target_material_free(owner);status("PASS","NONE");return 0;}/* A future authorization revision replaces this terminal fence with the
  * already-built D277 GUsb binding plus GoodixSecureSession.  Keeping it
  * closed here makes accidental execution in D278/02 hardware-inert. */goodix_target_material_free(owner);status("FAIL","CURRENT_LIVE_NOT_AUTHORIZED");return 1;}
