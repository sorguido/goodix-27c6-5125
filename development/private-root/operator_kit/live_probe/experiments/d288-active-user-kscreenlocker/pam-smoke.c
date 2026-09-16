// SPDX-License-Identifier: GPL-2.0-or-later
#include <stdio.h>
#include <stdlib.h>

typedef struct pam_handle pam_handle_t;
struct pam_message { int msg_style; const char *msg; };
struct pam_response { char *resp; int resp_retcode; };
struct pam_conv {
  int (*conv) (int, const struct pam_message **, struct pam_response **, void *);
  void *appdata_ptr;
};
extern int pam_start (const char *, const char *, const struct pam_conv *, pam_handle_t **);
extern int pam_authenticate (pam_handle_t *, int);
extern int pam_end (pam_handle_t *, int);

static int
conversation (int count, const struct pam_message **messages,
              struct pam_response **responses, void *data)
{
  struct pam_response *result;
  int i;
  (void) messages; (void) data;
  if (count <= 0 || responses == NULL)
    return 19;
  result = calloc ((size_t) count, sizeof *result);
  if (result == NULL)
    return 19;
  for (i = 0; i < count; i++)
    {
      result[i].resp = calloc (1, 1);
      if (result[i].resp == NULL)
        return 19;
    }
  *responses = result;
  return 0;
}

int
main (void)
{
  const struct pam_conv conv = { conversation, NULL };
  pam_handle_t *handle = NULL;
  int start = pam_start ("kde-fingerprint", NULL, &conv, &handle);
  int auth = start == 0 ? pam_authenticate (handle, 0) : start;
  int end = start == 0 ? pam_end (handle, auth) : start;
  printf ("D288_PAM_SMOKE_START=%d\nD288_PAM_SMOKE_AUTH=%d\nD288_PAM_SMOKE_END=%d\n",
          start, auth, end);
  return start == 0 && auth == 0 && end == 0 ? 0 : 1;
}
