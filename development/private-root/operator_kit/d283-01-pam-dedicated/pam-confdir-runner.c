// SPDX-License-Identifier: GPL-2.0-or-later
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

int
main (int argc, char **argv)
{
  const struct pam_conv conv = { conversation, NULL };
  pam_handle_t *handle = NULL;
  int start_result, auth_result, end_result;

  if (argc != 3 || argv[1][0] != '/' || argv[2][0] == '\0')
    {
      fprintf (stderr, "Uso: %s <directory-pam-assoluta> <utente>\n", argv[0]);
      return 2;
    }
  start_result = pam_start_confdir ("goodix-d283-01", argv[2], &conv,
                                    argv[1], &handle);
  printf ("D283_01_PAM_START_CONFDIR_RETURN_CODE=%d\n", start_result);
  if (start_result != PAM_SUCCESS)
    return 1;
  auth_result = pam_authenticate (handle, 0);
  printf ("D283_01_PAM_AUTHENTICATE_RETURN_CODE=%d\n", auth_result);
  end_result = pam_end (handle, auth_result);
  printf ("D283_01_PAM_END_RETURN_CODE=%d\n", end_result);
  return auth_result == PAM_SUCCESS && end_result == PAM_SUCCESS ? 0 : 1;
}
