/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Sudo-specific, password-first PAM conversation. No terminal I/O, password
 * verification, persistent counter or device protocol is implemented here. */
#define _GNU_SOURCE
#define PAM_SM_AUTH
#include <security/pam_modules.h>
#include <security/pam_appl.h>
#include <security/pam_ext.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pwd.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <syslog.h>
#include <time.h>
#include <unistd.h>

#define STATE_KEY "goodix-sudo-attempts-v1"
#define CHILD_SERVICE "goodix-sudo-fingerprint"
#define ATTEMPT_MS 8000
struct state { unsigned used; int disabled; pid_t child; };

static long long milliseconds(void)
{
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t)) return -1;
  return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static int expired(long long start, long long limit)
{
  long long now = milliseconds();
  return start < 0 || now < start || now - start >= limit;
}
static void stop_child(struct state *s)
{
  if (s->child <= 0) return;
  int status;
  pid_t r = waitpid(s->child, &status, WNOHANG);
  if (r == s->child || (r < 0 && errno == ECHILD)) { s->child = -1; return; }
  kill(s->child, SIGKILL);
  long long start = milliseconds();
  do {
    r = waitpid(s->child, &status, WNOHANG);
    if (r == s->child || (r < 0 && errno == ECHILD)) { s->child = -1; return; }
    struct timespec pause = {0, 1000000};
    nanosleep(&pause, NULL);
  } while (!expired(start, 100));
}
static void cleanup(pam_handle_t *p, void *data, int status)
{
  (void)p; (void)status;
  struct state *s = data;
  stop_child(s);
  free(s);
}
static int local_user(const char *name)
{
  FILE *f = fopen("/etc/passwd", "re");
  if (!f) return 0;
  struct passwd *e;
  int found = 0;
  while ((e = fgetpwent(f)))
    if (e->pw_uid && !strcmp(e->pw_name, name)) { found = 1; break; }
  fclose(f);
  return found;
}
/* sudo blocks INT/QUIT around pam_authenticate and unblocks them during its
 * password conversation. Observe pending cancellation without consuming it
 * or replacing the application's signal handlers/mask. */
static int interrupted(void)
{
  sigset_t pending;
  return sigpending(&pending) < 0 || sigismember(&pending, SIGINT) ||
         sigismember(&pending, SIGQUIT);
}
static int information_only(int n, const struct pam_message **m,
                            struct pam_response **r, void *data)
{
  const struct pam_conv *original = data;
  if (n < 1 || n > PAM_MAX_NUM_MSG) return PAM_CONV_ERR;
  for (int i = 0; i < n; i++)
    if (m[i]->msg_style != PAM_TEXT_INFO && m[i]->msg_style != PAM_ERROR_MSG)
      return PAM_CONV_ERR;
  return original->conv(n, m, r, original->appdata_ptr);
}
static void child(pam_handle_t *parent, const char *user, pid_t expected, int fd)
{
  if (prctl(PR_SET_PDEATHSIG, SIGKILL) || getppid() != expected) _exit(PAM_SYSTEM_ERR);
  const struct pam_conv *original = NULL;
  if (pam_get_item(parent, PAM_CONV, (const void **)&original) != PAM_SUCCESS ||
      !original || !original->conv) _exit(PAM_CONV_ERR);
  struct pam_conv conversation = {information_only, (void *)original};
  pam_handle_t *leaf = NULL;
  int result;
#ifdef GOODIX_SUDO_OFFLINE_TEST
  const char *directory = getenv("GOODIX_SUDO_TEST_CONFDIR");
  if (!directory || strncmp(directory, "/tmp/goodix-sudo-test.", 22)) _exit(PAM_SYSTEM_ERR);
  result = pam_start_confdir(CHILD_SERVICE, user, &conversation, directory, &leaf);
#else
  result = pam_start(CHILD_SERVICE, user, &conversation, &leaf);
#endif
  if (result == PAM_SUCCESS) {
    result = pam_authenticate(leaf, 0);
    pam_end(leaf, result);
  }
  _exit(write(fd, &result, sizeof result) == sizeof result ? 0 : PAM_SYSTEM_ERR);
}
static int attempt(pam_handle_t *p, struct state *s, const char *user)
{
  int fds[2];
  if (pipe2(fds, O_CLOEXEC | O_NONBLOCK)) return PAM_AUTHINFO_UNAVAIL;
  pid_t parent = getpid();
  s->child = fork();
  if (s->child == 0) { close(fds[0]); child(p, user, parent, fds[1]); }
  close(fds[1]);
  if (s->child < 0) { close(fds[0]); return PAM_AUTHINFO_UNAVAIL; }
  long long start = milliseconds();
  int result = PAM_AUTHINFO_UNAVAIL;
  while (!expired(start, ATTEMPT_MS)) {
    if (interrupted()) { result = PAM_ABORT; break; }
    int value;
    ssize_t n = read(fds[0], &value, sizeof value);
    if (n == sizeof value) { result = value; break; }
    if (n == 0 || (n < 0 && errno != EAGAIN && errno != EINTR)) break;
    struct pollfd completion = {fds[0], POLLIN, 0};
    if (poll(&completion, 1, 20) < 0 && errno != EINTR) break;
  }
  close(fds[0]);
  stop_child(s);
  if (interrupted()) return PAM_ABORT;
  if (s->child > 0) return PAM_AUTHINFO_UNAVAIL;
  return result;
}

PAM_EXTERN int pam_sm_authenticate(pam_handle_t *p, int flags, int argc, const char **argv)
{
  (void)flags; (void)argv;
  const void *service = NULL, *data = NULL;
  const char *user = NULL;
  if (argc || pam_get_item(p, PAM_SERVICE, &service) != PAM_SUCCESS || !service ||
      (strcmp(service, "sudo") && strcmp(service, "sudo-i"))) return PAM_IGNORE;
#ifndef GOODIX_SUDO_OFFLINE_TEST
  char executable[256];
  ssize_t n = readlink("/proc/self/exe", executable, sizeof executable - 1);
  if (geteuid() != 0 || n < 0 || !isatty(STDIN_FILENO)) return PAM_IGNORE;
  executable[n] = 0;
  if (strcmp(executable, "/usr/bin/sudo")) return PAM_IGNORE;
#endif
  if (pam_get_user(p, &user, NULL) != PAM_SUCCESS || !user || !local_user(user)) return PAM_IGNORE;
  struct state *s;
  if (pam_get_data(p, STATE_KEY, &data) == PAM_SUCCESS) s = (struct state *)data;
  else {
    s = calloc(1, sizeof *s);
    if (!s) return PAM_IGNORE;
    s->child = -1;
    if (pam_set_data(p, STATE_KEY, s, cleanup) != PAM_SUCCESS) { free(s); return PAM_IGNORE; }
  }
  if (s->disabled || s->used >= 3) return PAM_IGNORE;
  while (s->used < 3) {
    if (interrupted()) { s->disabled = 1; return PAM_ABORT; }
    const char *token = NULL;
    int r = pam_get_authtok(p, PAM_AUTHTOK, &token,
        "Password, or Enter for one fingerprint attempt (up to 8 seconds): ");
    if (r != PAM_SUCCESS || !token) { s->disabled = 1; return PAM_ABORT; }
    if (*token) { s->disabled = 1; return PAM_IGNORE; }
    if (pam_set_item(p, PAM_AUTHTOK, NULL) != PAM_SUCCESS) return PAM_ABORT;
    s->used++;
    pam_syslog(p, LOG_NOTICE, "GOODIX_SUDO fingerprint_choice=%u limit=3 max_child_actions=1", s->used);
    r = attempt(p, s, user);
    pam_syslog(p, LOG_NOTICE, "GOODIX_SUDO result=%s", r == PAM_SUCCESS ? "MATCH" :
               r == PAM_MAXTRIES ? "NO_MATCH" : r == PAM_ABORT ? "CANCEL" : "PASSWORD");
    if (r == PAM_SUCCESS) { s->disabled = 1; return PAM_SUCCESS; }
    if (r == PAM_ABORT) { s->disabled = 1; return PAM_ABORT; }
    if (r != PAM_MAXTRIES) break;
    /* Only explicit Enter after a completed NO MATCH can start another leaf.
     * PAM data persists across sudo's passwd_tries; it cannot multiply 3x3. */
  }
  s->disabled = 1;
  return PAM_IGNORE;
}

/* sudo calls setcred after authentication, including after changing PAM_USER
 * to the run-as identity. This module establishes no supplementary credentials.
 * Returning success here only acknowledges that no-op; it never authenticates. */
PAM_EXTERN int pam_sm_setcred(pam_handle_t *p, int flags, int argc, const char **argv)
{
  (void)p; (void)flags; (void)argc; (void)argv;
  return PAM_SUCCESS;
}
