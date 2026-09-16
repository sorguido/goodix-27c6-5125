// SPDX-License-Identifier: GPL-2.0-or-later
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct pam_handle pam_handle_t;
struct pam_message { int msg_style; const char *msg; };
struct pam_response { char *resp; int resp_retcode; };
struct pam_conv {
  int (*conv) (int, const struct pam_message **, struct pam_response **, void *);
  void *appdata_ptr;
};

typedef int (*pam_start_fn) (const char *, const char *, const struct pam_conv *,
                            pam_handle_t **);
typedef int (*pam_start_confdir_fn) (const char *, const char *,
                                    const struct pam_conv *, const char *,
                                    pam_handle_t **);

int
pam_start (const char *service, const char *user, const struct pam_conv *conv,
           pam_handle_t **handle)
{
  const char *directory = getenv ("GOODIX_D288_PAM_CONFDIR");
  pam_start_fn original;
  pam_start_confdir_fn redirected;

  dlerror ();
  if (service != NULL && strcmp (service, "kde-fingerprint") == 0 &&
      directory != NULL && directory[0] == '/')
    {
      *(void **) (&redirected) = dlsym (RTLD_NEXT, "pam_start_confdir");
      if (redirected == NULL)
        {
          fputs ("D288_PAM_REDIRECT_ERROR=PAM_START_CONFDIR_NOT_FOUND\n", stderr);
          return 4;
        }
      fputs ("D288_PAM_REDIRECT_SERVICE=kde-fingerprint\n", stderr);
      return redirected (service, user, conv, directory, handle);
    }
  *(void **) (&original) = dlsym (RTLD_NEXT, "pam_start");
  if (original == NULL)
    {
      fputs ("D288_PAM_REDIRECT_ERROR=PAM_START_NOT_FOUND\n", stderr);
      return 4;
    }
  return original (service, user, conv, handle);
}
