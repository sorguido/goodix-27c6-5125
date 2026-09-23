/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Offline test executable and PAM doubles. Never calls fprintd or D-Bus. */
#define _GNU_SOURCE
#define PAM_SM_AUTH
#include <security/pam_modules.h>
#include <security/pam_appl.h>
#include <security/pam_ext.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pwd.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>

#ifdef TEST_MODULE
PAM_EXTERN int pam_sm_authenticate(pam_handle_t *p, int f, int n, const char **a)
{
  (void)f;
  if (n != 1) return PAM_AUTH_ERR;
  if (!strcmp(a[0], "password")) {
    const char *token;
    int r = pam_get_authtok(p, PAM_AUTHTOK, &token, NULL);
    return r == PAM_SUCCESS && token && !strcmp(token, "offline-password") ? PAM_SUCCESS : PAM_AUTH_ERR;
  }
  const char *marker = getenv("GOODIX_SUDO_TEST_MARKER");
  if (!marker || strncmp(marker, "/tmp/goodix-sudo-test.", 22)) return PAM_AUTH_ERR;
  int fd = open(marker, O_WRONLY | O_CREAT | O_APPEND, 0600);
  if (fd < 0) return PAM_AUTH_ERR;
  dprintf(fd, "%ld\n", (long)getpid()); close(fd);
  pam_info(p, "OFFLINE_FINGERPRINT_STARTED");
  const char *mode = getenv("GOODIX_SUDO_TEST_MODE");
  if (!mode) return PAM_AUTH_ERR;
  if (!strcmp(mode, "block")) for (;;) pause();
  if (!strcmp(mode, "no-match")) return PAM_MAXTRIES;
  if (!strcmp(mode, "unavailable")) return PAM_AUTHINFO_UNAVAIL;
  if (!strcmp(mode, "prompt")) {
    const char *token;
    return pam_get_authtok(p, PAM_AUTHTOK, &token, NULL);
  }
  if (!strcmp(mode, "match-second")) {
    FILE *file = fopen(marker, "r");
    int count = 0, c;
    while ((c = fgetc(file)) != EOF) count += c == '\n';
    fclose(file);
    return count == 2 ? PAM_SUCCESS : PAM_MAXTRIES;
  }
  return !strcmp(mode, "match") ? PAM_SUCCESS : PAM_AUTH_ERR;
}
PAM_EXTERN int pam_sm_acct_mgmt(pam_handle_t *p, int f, int n, const char **a)
{
  (void)p; (void)f; (void)n; (void)a;
  return getenv("GOODIX_SUDO_TEST_ACCOUNT_FAIL") ? PAM_PERM_DENIED : PAM_SUCCESS;
}
PAM_EXTERN int pam_sm_setcred(pam_handle_t *p, int f, int n, const char **a)
{
  (void)p; (void)f; (void)n; (void)a;
  return PAM_SUCCESS;
}
#else
/* Only this offline executable disables kernel audit: sandbox NETLINK_AUDIT
 * returns EPERM at audit_open, which libpam treats as a system error even
 * with all-synthetic PAM services. Production retains Fedora audit unchanged. */
int audit_open(void) { errno = EPROTONOSUPPORT; return -1; }
static int conversation(int n, const struct pam_message **m, struct pam_response **r, void *data)
{
  (void)data;
  *r = calloc((size_t)n, sizeof **r);
  if (!*r) return PAM_BUF_ERR;
  for (int i = 0; i < n; i++) {
    if (m[i]->msg_style == PAM_PROMPT_ECHO_OFF || m[i]->msg_style == PAM_PROMPT_ECHO_ON) {
      char buffer[PAM_MAX_RESP_SIZE];
      puts("PROMPT"); fflush(stdout);
      if (!fgets(buffer, sizeof buffer, stdin)) { free(*r); *r = NULL; return PAM_CONV_ERR; }
      buffer[strcspn(buffer, "\n")] = 0;
      (*r)[i].resp = strdup(buffer);
      explicit_bzero(buffer, sizeof buffer);
    } else {
      printf("INFO:%s\n", m[i]->msg); fflush(stdout);
    }
  }
  return PAM_SUCCESS;
}
int main(int argc, char **argv)
{
  if (argc != 3) return 2;
  sigset_t mask; sigemptyset(&mask); sigaddset(&mask, SIGINT); sigaddset(&mask, SIGQUIT);
  sigprocmask(SIG_BLOCK, &mask, NULL);
  if (getenv("GOODIX_SUDO_TEST_COOKIE")) {
    char dummy[128];
    if (!fgets(dummy, sizeof dummy, stdin)) return 2;
  }
  struct pam_conv conv = {conversation, NULL};
  pam_handle_t *p = NULL;
  int r = pam_start_confdir(argv[2], (getenv("GOODIX_SUDO_TEST_USER") ? getenv("GOODIX_SUDO_TEST_USER") : getpwuid(getuid())->pw_name), &conv, argv[1], &p);
  int times = getenv("GOODIX_SUDO_TEST_REPEAT") ? 3 : 1;
  if (r == PAM_SUCCESS) for (int i = 0; i < times; i++) {
    r = pam_authenticate(p, PAM_SILENT);
    if (r == PAM_SUCCESS) break;
  }
  printf("AUTH_RESULT=%d\n", r);
  if (r == PAM_SUCCESS) r = pam_acct_mgmt(p, 0);
  if (r == PAM_SUCCESS) r = pam_setcred(p, PAM_REINITIALIZE_CRED);
  if (p) pam_end(p, r);
  printf("RESULT=%d\n", r);
  return r == PAM_SUCCESS ? 0 : 1;
}
#endif
