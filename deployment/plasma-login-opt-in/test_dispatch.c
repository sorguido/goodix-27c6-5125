/* SPDX-License-Identifier: GPL-2.0-or-later */
/* VM-only synthetic Linux-PAM unit test. Never loads a real auth module. */
#include <security/pam_appl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef BUILD_MODULE
#include <security/pam_modules.h>

static const char *option(int argc, const char **argv, const char *key,
                          const char *fallback)
{
    size_t length = strlen(key);
    for (int i = 0; i < argc; i++)
        if (!strncmp(argv[i], key, length) && argv[i][length] == '=')
            return argv[i] + length + 1;
    return fallback;
}

static int mock(pam_handle_t *pamh, int argc, const char **argv,
                const char *phase)
{
    const char *path = pam_getenv(pamh, "GOODIX_SYNTHETIC_LOG");
    const char *role = option(argc, argv, "role", "unknown");
    const char *result = option(argc, argv, phase, "success");
    FILE *file = path ? fopen(path, "a") : NULL;
    if (!file)
        return PAM_SYSTEM_ERR;
    int failed = fprintf(file, "%s.%s\n", role, phase) < 0;
    if (fclose(file) || failed)
        return PAM_SYSTEM_ERR;
    const char *expected = option(argc, argv, "expect_token", NULL);
    if (expected && !strcmp(phase, "auth")) {
        const void *token = NULL;
        if (pam_get_item(pamh, PAM_AUTHTOK, &token) != PAM_SUCCESS ||
            token == NULL || strcmp(token, expected))
            return PAM_AUTH_ERR;
    }
    if (!strcmp(result, "success")) return PAM_SUCCESS;
    if (!strcmp(result, "ignore")) return PAM_IGNORE;
    if (!strcmp(result, "auth_err")) return PAM_AUTH_ERR;
    if (!strcmp(result, "module_unknown")) return PAM_MODULE_UNKNOWN;
    return PAM_SYSTEM_ERR;
}

#define MOCK_ENTRY(function, phase) \
    int function(pam_handle_t *pamh, int flags, int argc, const char **argv) \
    { (void)flags; return mock(pamh, argc, argv, phase); }
MOCK_ENTRY(pam_sm_authenticate, "auth")
MOCK_ENTRY(pam_sm_setcred, "cred")
MOCK_ENTRY(pam_sm_acct_mgmt, "account")
MOCK_ENTRY(pam_sm_open_session, "open")
MOCK_ENTRY(pam_sm_close_session, "close")
MOCK_ENTRY(pam_sm_chauthtok, "password")

#else
struct synthetic_reply { const char *token; unsigned int calls; };

static int conversation(int count, const struct pam_message **messages,
                        struct pam_response **responses, void *data)
{
    struct synthetic_reply *reply = data;
    if (!reply || reply->calls++ || count != 1 ||
        messages[0]->msg_style != PAM_PROMPT_ECHO_OFF)
        return PAM_CONV_ERR;
    *responses = calloc(1, sizeof(**responses));
    if (!*responses)
        return PAM_BUF_ERR;
    size_t length = strlen(reply->token) + 1;
    (*responses)[0].resp = malloc(length);
    if (!(*responses)[0].resp) { free(*responses); *responses = NULL; return PAM_BUF_ERR; }
    memcpy((*responses)[0].resp, reply->token, length);
    return PAM_SUCCESS;
}

int main(int argc, char **argv)
{
    pam_handle_t *pamh = NULL;
    struct synthetic_reply reply = {"", 0};
    struct pam_conv callback = {conversation, NULL};
    int auth = -1, account = -1, cred = -1, open = -1, close = -1;
    if ((argc != 3 && argc != 4) || argv[1][0] != '/' || argv[2][0] != '/')
        return 2;
    if (argc == 4) {
        if (!strcmp(argv[3], "nonempty")) reply.token = "synthetic-password";
        else if (strcmp(argv[3], "empty")) return 2;
        callback.appdata_ptr = &reply;
    }
    int result = pam_start_confdir("goodix-opt-in-synthetic", "synthetic-user",
                                   &callback, argv[1], &pamh);
    if (result != PAM_SUCCESS)
        return 3;
    size_t length = strlen(argv[2]) + sizeof("GOODIX_SYNTHETIC_LOG=");
    char *environment = malloc(length);
    if (!environment) { pam_end(pamh, PAM_BUF_ERR); return 4; }
    snprintf(environment, length, "GOODIX_SYNTHETIC_LOG=%s", argv[2]);
    result = pam_putenv(pamh, environment);
    free(environment);
    if (result != PAM_SUCCESS) { pam_end(pamh, result); return 5; }
    result = auth = pam_authenticate(pamh, 0);
    if (result == PAM_SUCCESS) result = account = pam_acct_mgmt(pamh, 0);
    if (result == PAM_SUCCESS) result = cred = pam_setcred(pamh, PAM_ESTABLISH_CRED);
    if (result == PAM_SUCCESS) result = open = pam_open_session(pamh, 0);
    if (result == PAM_SUCCESS) result = close = pam_close_session(pamh, 0);
    pam_end(pamh, result);
    printf("%d %d %d %d %d\n", auth, account, cred, open, close);
    return 0;
}
#endif
