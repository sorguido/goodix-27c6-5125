// SPDX-License-Identifier: GPL-2.0-or-later
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

typedef struct pam_handle pam_handle_t;
struct pam_message { int msg_style; const char *msg; };
struct pam_response { char *resp; int resp_retcode; };
struct pam_conv {
  int (*conv) (int, const struct pam_message **,
               struct pam_response **, void *);
  void *appdata_ptr;
};

extern int pam_start_confdir (const char *, const char *,
                              const struct pam_conv *, const char *,
                              pam_handle_t **);
extern int pam_authenticate (pam_handle_t *, int);
extern int pam_end (pam_handle_t *, int);

enum { PAM_SUCCESS = 0, PAM_CONV_ERR = 19 };

static int
conversation (int count, const struct pam_message **messages,
              struct pam_response **responses, void *data)
{
  struct pam_response *result;
  int i;

  (void) data;
  if (count <= 0 || messages == NULL || responses == NULL)
    return PAM_CONV_ERR;
  result = calloc ((size_t) count, sizeof *result);
  if (result == NULL)
    return PAM_CONV_ERR;
  for (i = 0; i < count; i++)
    {
      if (messages[i] != NULL && messages[i]->msg != NULL)
        fprintf (stderr, "PAM: %s\n", messages[i]->msg);
      result[i].resp = strdup ("");
      if (result[i].resp == NULL)
        {
          while (i-- > 0)
            free (result[i].resp);
          free (result);
          return PAM_CONV_ERR;
        }
    }
  *responses = result;
  return PAM_SUCCESS;
}

static int
read_start_time (unsigned long long *result)
{
  char line[4096];
  char *cursor;
  char *saveptr = NULL;
  char *token;
  char *end;
  FILE *file;
  int field;

  file = fopen ("/proc/self/stat", "re");
  if (file == NULL)
    return -1;
  if (fgets (line, sizeof line, file) == NULL)
    {
      fclose (file);
      return -1;
    }
  fclose (file);
  cursor = strrchr (line, ')');
  if (cursor == NULL || cursor[1] != ' ')
    return -1;
  cursor += 2;
  token = strtok_r (cursor, " ", &saveptr);
  for (field = 3; field < 22 && token != NULL; field++)
    token = strtok_r (NULL, " ", &saveptr);
  if (token == NULL)
    return -1;
  errno = 0;
  *result = strtoull (token, &end, 10);
  return errno == 0 && end != token && (*end == '\0' || *end == '\n') ? 0 : -1;
}

static void
print_cgroup (void)
{
  char line[4096];
  char *path;
  FILE *file = fopen ("/proc/self/cgroup", "re");

  if (file == NULL || fgets (line, sizeof line, file) == NULL)
    {
      if (file != NULL)
        fclose (file);
      puts ("D287_01_PROBE_RUNNER_CGROUP=UNKNOWN");
      return;
    }
  fclose (file);
  line[strcspn (line, "\r\n")] = '\0';
  path = strrchr (line, ':');
  printf ("D287_01_PROBE_RUNNER_CGROUP=%s\n", path == NULL ? "UNKNOWN" : path + 1);
}

static int
check_exact_polkit_subject (void)
{
  unsigned long long start_time;
  char subject[128];
  pid_t child;
  int status;

  if (read_start_time (&start_time) != 0)
    {
      puts ("D287_01_PROBE_POLKIT_SUBJECT_BUILD=FAIL");
      return -1;
    }
  if (snprintf (subject, sizeof subject, "%ld,%llu,%ld", (long) getpid (),
                start_time, (long) getuid ()) >= (int) sizeof subject)
    return -1;
  printf ("D287_01_PROBE_POLKIT_SUBJECT_PID=%ld\n", (long) getpid ());
  printf ("D287_01_PROBE_POLKIT_SUBJECT_START_TIME=%llu\n", start_time);
  printf ("D287_01_PROBE_POLKIT_SUBJECT_UID=%ld\n", (long) getuid ());
  print_cgroup ();
  fflush (NULL);

  child = fork ();
  if (child < 0)
    return -1;
  if (child == 0)
    {
      execl ("/usr/bin/pkcheck", "pkcheck", "--action-id",
             "net.reactivated.fprint.device.verify", "--process", subject,
             (char *) NULL);
      _exit (127);
    }
  if (waitpid (child, &status, 0) != child)
    return -1;
  if (!WIFEXITED (status))
    return -1;
  printf ("D287_01_PROBE_PKCHECK_RETURN_CODE=%d\n", WEXITSTATUS (status));
  if (WEXITSTATUS (status) != 0)
    return -1;
  puts ("D287_01_PROBE_ACTIVE_USER_POLKIT_PREFLIGHT=PASS");
  fflush (NULL);
  return 0;
}

int
main (int argc, char **argv)
{
  const struct pam_conv conv = { conversation, NULL };
  const char *service;
  pam_handle_t *handle = NULL;
  int start_result;
  int auth_result;
  int end_result;
  int active_probe;

  if (argc != 4 || argv[2][0] != '/' || argv[3][0] == '\0')
    {
      fprintf (stderr, "Uso: %s --offline-permit|--active-user-probe <directory-pam-assoluta> <utente>\n", argv[0]);
      return 2;
    }
  active_probe = strcmp (argv[1], "--active-user-probe") == 0;
  if (active_probe)
    service = "goodix-d287-01-active-user";
  else if (strcmp (argv[1], "--offline-permit") == 0)
    service = "goodix-d287-01-offline-permit";
  else
    return 2;

  if (active_probe)
    {
      if (getuid () == 0 || geteuid () == 0 || getuid () != geteuid ())
        {
          puts ("D287_01_PROBE_UNPRIVILEGED_IDENTITY=FAIL");
          return 3;
        }
      puts ("D287_01_PROBE_UNPRIVILEGED_IDENTITY=PASS");
      if (check_exact_polkit_subject () != 0)
        {
          puts ("D287_01_PROBE_ACTIVE_USER_POLKIT_PREFLIGHT=FAIL");
          puts ("D287_01_PROBE_PAM_NOT_STARTED=true");
          return 3;
        }
    }

  start_result = pam_start_confdir (service, argv[3], &conv, argv[2], &handle);
  printf ("D287_01_PROBE_PAM_START_CONFDIR_RETURN_CODE=%d\n", start_result);
  if (start_result != PAM_SUCCESS)
    return 1;
  auth_result = pam_authenticate (handle, 0);
  printf ("D287_01_PROBE_PAM_AUTHENTICATE_RETURN_CODE=%d\n", auth_result);
  end_result = pam_end (handle, auth_result);
  printf ("D287_01_PROBE_PAM_END_RETURN_CODE=%d\n", end_result);
  return auth_result == PAM_SUCCESS && end_result == PAM_SUCCESS ? 0 : 1;
}
