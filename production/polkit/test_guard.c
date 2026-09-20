/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Execute the production open_guard with virtual root metadata only. Real
 * syscalls remain uid 1000 in /tmp; no PAM authentication, bus or device. */
#include "pam_goodix_polkit.c"
#include <stdarg.h>
#include <assert.h>

static const char *test_directory;
static gid_t virtual_gid = 1000; /* egid inherited by the setuid helper */
static int changes, fail_chown;
int __real_open(const char *, int, ...);
int __real_fstat(int, struct stat *);

int __wrap_open(const char *name, int flags, ...)
{
  assert(!(flags & O_CREAT));
  assert(strcmp(name, GUARD_DIRECTORY) == 0);
  return __real_open(test_directory, flags);
}

int __wrap_fstat(int fd, struct stat *s)
{
  int result = __real_fstat(fd, s);
  if (!result) {
    s->st_uid = 0;
    s->st_gid = S_ISDIR(s->st_mode) ? 0 : virtual_gid;
  }
  return result;
}

int __wrap_fchown(int fd, uid_t uid, gid_t gid)
{
  struct stat s;
  assert(__real_fstat(fd, &s) == 0 && S_ISREG(s.st_mode));
  assert(uid == 0 && gid == 0);
  changes++;
  if (fail_chown) { errno = EPERM; return -1; }
  virtual_gid = gid;
  return 0;
}

int __wrap_pam_set_data(pam_handle_t *p, const char *key, void *data,
                       void (*cleanup)(pam_handle_t *, void *, int))
{
  (void)p; (void)data;
  assert(strcmp(key, GUARD_KEY) == 0 && cleanup == guard_cleanup);
  return PAM_SUCCESS;
}

int main(int argc, char **argv)
{
  assert(getuid() != 0 && geteuid() != 0 && argc == 3);
  test_directory = argv[1];
  assert(strncmp(test_directory, "/tmp/goodix-", 12) == 0);
  fail_chown = !strcmp(argv[2], "fail");
  unsigned used = 99;
  struct guard *g = open_guard(NULL, 1000, &used);
  assert(changes == 1);
  if (fail_chown) { assert(!g); return 0; }
  assert(g && used == 0 && virtual_gid == 0);
  guard_cleanup(NULL, g, PAM_SUCCESS);
  g = open_guard(NULL, 1000, &used);
  assert(g && used == 0 && changes == 1);
  guard_cleanup(NULL, g, PAM_SUCCESS);
  puts("VIRTUAL_EUID=0 INHERITED_EGID=1000 COUNTER_UID=0 COUNTER_GID=0");
  return 0;
}
