/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Service-local conversation bridge. The child uses Fedora pam_fprintd;
 * the parent never validates passwords or implements device commands. */
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
#include <sys/file.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <syslog.h>
#include <time.h>
#include <unistd.h>

#define GUARD_DIRECTORY "/run/polkit/goodix-fingerprint"
#define CHILD_SERVICE "goodix-polkit-fingerprint"
#define GUARD_KEY "goodix-polkit-conversation-v1"
#define MAX_CHOICES 3

struct guard {
  int fd;
  pid_t child;
};

static long long
milliseconds(void)
{
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t) < 0) return -1;
  return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

static int
expired(long long start, long long limit)
{
  long long now = milliseconds();
  return start < 0 || now < start || now - start >= limit;
}

/* Use stdio, not only poll(fd): read_cookie()/the initial PAM conversation
 * may already have buffered the next response. No password byte is retained,
 * parsed, logged or removed from the helper's stream. */
static int
input_pending(FILE *stream)
{
  int fd = fileno(stream), result = -1;
  flockfile(stream);
  int flags = fcntl(fd, F_GETFL);
  if (flags < 0 || ferror(stream) || feof(stream)) goto out;
  if (fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) goto out;
  errno = 0;
  int c = fgetc(stream);
  if (c != EOF)
    result = ungetc(c, stream) == c ? 1 : -1;
  else if (ferror(stream) && (errno == EAGAIN || errno == EWOULDBLOCK)) {
    clearerr(stream);
    result = 0;
  }
  /* EOF, stream failure, or failed restoration disables fingerprint. */
  if (fcntl(fd, F_SETFL, flags) < 0) result = -1;
out:
  funlockfile(stream);
  return result;
}

static void
stop_child(struct guard *g)
{
  if (g->child <= 0) return;
  int status;
  pid_t waited = waitpid(g->child, &status, WNOHANG);
  if (waited == g->child || (waited < 0 && errno == ECHILD)) {
    g->child = -1;
    return;
  }
  /* Closing the child's D-Bus connection invokes fprintd's owner-loss
   * cancellation/close path. Never wait for the fingerprint timeout. */
  kill(g->child, SIGKILL);
  long long start = milliseconds();
  do {
    pid_t result = waitpid(g->child, &status, WNOHANG);
    if (result == g->child || (result < 0 && errno == ECHILD)) {
      g->child = -1;
      return;
    }
    struct timespec pause = {0, 1000000};
    nanosleep(&pause, NULL);
  } while (!expired(start, 100));
  /* A killed child stuck in the kernel must not stall password PAM. It
   * remains our child until reaped; cleanup gets one further bounded try. */
}

static void
guard_cleanup(pam_handle_t *pamh, void *data, int status)
{
  struct guard *g = data;
  stop_child(g);
  /* Reset on the helper's successful PAM teardown, after authentication and
   * account checks. Failure/cancel/crash retain the count. This does not claim
   * that Polkit has already granted the requested action. Keep the lock for
   * the whole PAM handle. */
  if (status == PAM_SUCCESS && g->fd >= 0) {
    if (pwrite(g->fd, "0", 1, 0) != 1 || ftruncate(g->fd, 1) < 0)
      pam_syslog(pamh, LOG_ERR, "GOODIX_POLKIT counter_reset_failed");
  }
  if (g->fd >= 0) close(g->fd);
  free(g);
}

static int
local_uid(const char *name, uid_t *uid)
{
  FILE *file = fopen("/etc/passwd", "re");
  if (!file) return -1;
  struct passwd *entry;
  int result = -1;
  while ((entry = fgetpwent(file))) {
    if (strcmp(entry->pw_name, name) == 0 && entry->pw_uid != 0) {
      *uid = entry->pw_uid;
      result = 0;
      break;
    }
  }
  fclose(file);
  return result;
}

static struct guard *
failed_guard(int dir, const char *name, int fd, int fresh)
{
  struct stat opened, named;
  /* Failed initialization must not strand our own empty/noncanonical inode.
   * Existing counters, substituted names and extra links are never removed. */
  if (fresh && fstat(fd, &opened) == 0 &&
      fstatat(dir, name, &named, AT_SYMLINK_NOFOLLOW) == 0 &&
      opened.st_dev == named.st_dev && opened.st_ino == named.st_ino &&
      opened.st_nlink == 1)
    unlinkat(dir, name, 0);
  if (fd >= 0) close(fd);
  close(dir);
  return NULL;
}

static struct guard *
open_guard(pam_handle_t *pamh, uid_t uid, unsigned *used)
{
  const char *directory = GUARD_DIRECTORY;
  uid_t owner = 0;
  gid_t group = 0;
#ifdef GOODIX_POLKIT_OFFLINE_TEST
  directory = getenv("GOODIX_POLKIT_TEST_GUARD");
  owner = geteuid();
  group = getegid();
  if (!directory || strncmp(directory, "/tmp/goodix-polkit-test.", 24)) return NULL;
#endif
  struct stat s;
  int dir = open(directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (dir < 0) return NULL;
  if (fstat(dir, &s) < 0 || s.st_uid != owner || s.st_gid != group ||
      (s.st_mode & 07777) != 0700) {
    close(dir); return NULL;
  }
  char filename[32];
  snprintf(filename, sizeof filename, "%lu", (unsigned long)uid);
  int fd = openat(dir, filename, O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
  int fresh = fd >= 0;
  if (fd < 0 && errno == EEXIST &&
      fstatat(dir, filename, &s, AT_SYMLINK_NOFOLLOW) == 0 && S_ISREG(s.st_mode))
    fd = openat(dir, filename, O_RDWR | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
  if (fd < 0) return failed_guard(dir, filename, fd, 0);
  if (fstat(fd, &s) < 0 || !S_ISREG(s.st_mode) || s.st_uid != owner ||
      (s.st_mode & 07777) != 0600 || s.st_nlink != 1 ||
      flock(fd, LOCK_EX | LOCK_NB) < 0) return failed_guard(dir, filename, fd, fresh);
  char value = '3';
  if (fresh) {
    /* The setuid (not setgid) helper can retain the caller's egid. Never
     * inherit that group into our root-owned runtime contract. Only the
     * O_EXCL inode just created here may be normalized. */
    if (fchown(fd, owner, group) < 0 || fstat(fd, &s) < 0 ||
        s.st_uid != owner || s.st_gid != group ||
        (s.st_mode & 07777) != 0600 || s.st_nlink != 1) {
      return failed_guard(dir, filename, fd, fresh);
    }
    if (pwrite(fd, "0", 1, 0) != 1) return failed_guard(dir, filename, fd, fresh);
    value = '0';
  } else if (s.st_gid != group || s.st_size != 1 || pread(fd, &value, 1, 0) != 1 ||
             value < '0' || value > '3') {
    /* Foreign or corrupt state is preserved, including on password success.
     * Historical noncanonical counters are handled by qualified uninstall. */
    return failed_guard(dir, filename, fd, 0);
  }
  close(dir);
  struct guard *g = calloc(1, sizeof *g);
  if (!g) { close(fd); return NULL; }
  g->fd = fd;
  g->child = -1;
  if (pam_set_data(pamh, GUARD_KEY, g, guard_cleanup) != PAM_SUCCESS) {
    close(fd); free(g); return NULL;
  }
  *used = (unsigned)(value - '0');
  return g;
}

/* The leaf must never request or inherit a password. Forward only the
 * informational messages expected by Polkit's original PAM conversation. */
static int
child_conversation(int n, const struct pam_message **messages,
                   struct pam_response **response, void *data)
{
  const struct pam_conv *original = data;
  if (n < 1 || n > PAM_MAX_NUM_MSG) return PAM_CONV_ERR;
  for (int i = 0; i < n; i++)
    if (messages[i]->msg_style != PAM_TEXT_INFO && messages[i]->msg_style != PAM_ERROR_MSG)
      return PAM_CONV_ERR;
  return original->conv(n, messages, response, original->appdata_ptr);
}

static void
fingerprint_child(pam_handle_t *parent, struct guard *g, const char *user,
                  pid_t expected_parent, int completion_fd)
{
  /* Covers cancellation of the whole KDE dialog and the fork/prctl race. */
  if (prctl(PR_SET_PDEATHSIG, SIGKILL) < 0 || getppid() != expected_parent) _exit(PAM_SYSTEM_ERR);
  close(g->fd);
  const struct pam_conv *original = NULL;
  if (pam_get_item(parent, PAM_CONV, (const void **)&original) != PAM_SUCCESS ||
      !original || !original->conv) _exit(PAM_CONV_ERR);
  struct pam_conv conversation = {child_conversation, (void *)original};
  pam_handle_t *child = NULL;
  int result;
#ifdef GOODIX_POLKIT_OFFLINE_TEST
  const char *confdir = getenv("GOODIX_POLKIT_TEST_CONFDIR");
  if (!confdir || strncmp(confdir, "/tmp/goodix-polkit-test.", 24)) _exit(PAM_SYSTEM_ERR);
  result = pam_start_confdir(CHILD_SERVICE, user, &conversation, confdir, &child);
#else
  result = pam_start(CHILD_SERVICE, user, &conversation, &child);
#endif
  if (result == PAM_SUCCESS) {
    result = pam_authenticate(child, 0);
    pam_end(child, result);
  }
  /* Only this pipe supplies a result; stdout retains the upstream protocol. */
  _exit(write(completion_fd, &result, sizeof result) == sizeof result ? 0 : PAM_SYSTEM_ERR);
}

PAM_EXTERN int
pam_sm_authenticate(pam_handle_t *pamh, int flags, int argc, const char **argv)
{
  (void)flags; (void)argv;
  const void *service = NULL, *existing = NULL;
  const char *user = NULL, *token = NULL;
  struct stat input;
  uid_t uid;
  if (argc || pam_get_item(pamh, PAM_SERVICE, &service) != PAM_SUCCESS ||
      !service || strcmp(service, "polkit-1") ||
      fstat(STDIN_FILENO, &input) < 0 || (!S_ISFIFO(input.st_mode) && !S_ISSOCK(input.st_mode)))
    return PAM_IGNORE;
#ifndef GOODIX_POLKIT_OFFLINE_TEST
  char executable[256];
  ssize_t length = readlink("/proc/self/exe", executable, sizeof executable - 1);
  if (geteuid() != 0 || length < 0) return PAM_IGNORE;
  executable[length] = 0;
  if (strcmp(executable, "/usr/lib/polkit-1/polkit-agent-helper-1")) return PAM_IGNORE;
#endif
  if (pam_get_data(pamh, GUARD_KEY, &existing) == PAM_SUCCESS) return PAM_AUTH_ERR;
  if (pam_get_user(pamh, &user, NULL) != PAM_SUCCESS || !user || local_uid(user, &uid) < 0)
    return PAM_IGNORE;
  unsigned used = MAX_CHOICES;
  struct guard *g = open_guard(pamh, uid, &used);
  if (!g || used >= MAX_CHOICES) {
    pam_info(pamh, "Fingerprint unavailable; use your password.");
    return PAM_IGNORE;
  }
  pam_info(pamh, "Enter your password, or submit an empty field to use fingerprint.");
  int result = pam_get_authtok(pamh, PAM_AUTHTOK, &token, NULL);
  if (result != PAM_SUCCESS || !token) return PAM_AUTH_ERR;
  if (*token) return PAM_IGNORE; /* pam_unix consumes the existing PAM token. */
  if (pam_set_item(pamh, PAM_AUTHTOK, NULL) != PAM_SUCCESS) return PAM_AUTH_ERR;
  if (input_pending(stdin) != 0) return PAM_IGNORE;
  char next = (char)('0' + used + 1);
  if (pwrite(g->fd, &next, 1, 0) != 1 || ftruncate(g->fd, 1) < 0) return PAM_AUTH_ERR;
  int completion[2];
  if (pipe2(completion, O_CLOEXEC | O_NONBLOCK) < 0) return PAM_IGNORE;
  pid_t parent = getpid();
  g->child = fork();
  if (g->child == 0) {
    close(completion[0]);
    fingerprint_child(pamh, g, user, parent, completion[1]);
  }
  close(completion[1]);
  if (g->child < 0) { close(completion[0]); return PAM_IGNORE; }
  pam_syslog(pamh, LOG_NOTICE, "GOODIX_POLKIT fingerprint_choice=%u limit=3 max_child_actions=1", used + 1);
  long long start = milliseconds();
  result = PAM_IGNORE;
  while (!expired(start, 45000)) {
    int pending = input_pending(stdin);
    if (pending != 0) {
      pam_syslog(pamh, LOG_NOTICE, "GOODIX_POLKIT fingerprint_cancelled_for_input");
      break;
    }
    int child_result;
    ssize_t count = read(completion[0], &child_result, sizeof child_result);
    if (count == sizeof child_result) {
      result = child_result == PAM_SUCCESS ? PAM_SUCCESS :
               child_result == PAM_MAXTRIES ? PAM_AUTH_ERR : PAM_IGNORE;
      break;
    }
    if (count == 0 || (count < 0 && errno != EAGAIN && errno != EINTR)) break;
    struct pollfd descriptors[2] = {{STDIN_FILENO, POLLIN, 0}, {completion[0], POLLIN, 0}};
    if (poll(descriptors, 2, 20) < 0 && errno != EINTR) break;
  }
  close(completion[0]);
  stop_child(g);
  pam_syslog(pamh, LOG_NOTICE, "GOODIX_POLKIT conversation_result=%s",
             result == PAM_SUCCESS ? "MATCH" : result == PAM_AUTH_ERR ? "NO_MATCH" : "PASSWORD");
  return result;
}
