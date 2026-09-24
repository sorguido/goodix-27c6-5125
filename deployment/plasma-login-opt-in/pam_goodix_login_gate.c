/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * An empty token selects fingerprint; this module never authenticates a user.
 * Its PAM_SUCCESS MUST have action "ignore" in the calling PAM configuration.
 * Every error or unfamiliar vendor auth policy disables fingerprint only.
 * No password copy, subprocess, device access, persistent state or logging.
 */
#define _POSIX_C_SOURCE 200809L
#include <security/pam_modules.h>
#include <security/pam_ext.h>

#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifdef GOODIX_GATE_TEST
#if !defined(GOODIX_GATE_VENDOR_PATH) || !defined(GOODIX_GATE_PASSWORD_PATH) || \
    !defined(GOODIX_GATE_POSTLOGIN_PATH)
#error "The unit test must provide all three fixture paths"
#endif
#else
#define GOODIX_GATE_VENDOR_PATH "/usr/lib/pam.d/plasmalogin"
#define GOODIX_GATE_PASSWORD_PATH "/etc/pam.d/password-auth"
#define GOODIX_GATE_POSTLOGIN_PATH "/etc/pam.d/postlogin"
#endif

/* Known auth structure from the Fedora 44 VM preflight, not a vendor copy.
 * Changes to auth policy require review before fingerprint can bypass it.
 * Password/account/session always use the current vendor configuration.
 */
static const char *const login_auth[] = {
    "auth [success=done ignore=ignore default=bad] pam_selinux_permit.so",
    "auth substack password-auth",
    "-auth optional pam_gnome_keyring.so",
    "-auth optional pam_kwallet5.so",
    "-auth optional pam_kwallet.so",
    "-auth optional pam_oo7.so",
    "auth include postlogin",
};
static const char *const password_auth[] = {
    "auth required pam_env.so",
    "auth required pam_faildelay.so delay=2000000",
    "auth sufficient pam_unix.so nullok",
    "auth required pam_deny.so",
};

/* This is deliberately not a PAM parser. Only the known auth rows are allowed.
 * Reject ambiguous syntax instead of trying to interpret future PAM policy.
 */
static int check_line(char *line, const char *const expected[], size_t count,
                      size_t *matched)
{
    char normalized[512];
    size_t length = 0;
    int space = 0;
    const unsigned char *p = (const unsigned char *)line;
    const char *type;

    /* Even a comment ending in backslash could consume the following row. */
    if (strchr(line, '\\') != NULL)
        return 0;
    while (*p == ' ' || *p == '\t')
        ++p;
    if (*p == '\0' || *p == '#')
        return 1;
    for (; *p != '\0'; ++p) {
        if (*p == ' ' || *p == '\t') {
            space = length != 0;
            continue;
        }
        if (*p < 33 || *p > 126 || *p == '\\' || *p == '#')
            return 0;
        if (space)
            normalized[length++] = ' ';
        normalized[length++] = (char)*p;
        space = 0;
    }
    normalized[length] = '\0';
    type = normalized[0] == '-' ? normalized + 1 : normalized;
    if (strncmp(type, "auth ", 5) == 0) {
        if (*matched == count || strcmp(normalized, expected[*matched]) != 0)
            return 0;
        ++*matched;
        return 1;
    }
    /* Current non-auth rows are delegated, never reproduced by this module. */
    return strncmp(type, "account ", 8) == 0 ||
           strncmp(type, "password ", 9) == 0 ||
           strncmp(type, "session ", 8) == 0;
}

static int auth_shape(const char *path, const char *const expected[], size_t count)
{
    char line[512];
    size_t used = 0, total = 0, lines = 0, matched = 0;
    struct stat st;
    int fd, ch, good = 0;
    FILE *stream;

    /* NONBLOCK prevents a malformed fixture/path becoming a blocking FIFO. */
    fd = open(path, O_RDONLY | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0)
        return 0;
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_size > 65536) {
        close(fd);
        return 0;
    }
    stream = fdopen(fd, "r");
    if (stream == NULL) {
        close(fd);
        return 0;
    }
    while ((ch = fgetc(stream)) != EOF) {
        if (++total > 65536 || ch == '\0')
            goto done;
        if (ch == '\n') {
            line[used] = '\0';
            if (++lines > 256 || !check_line(line, expected, count, &matched))
                goto done;
            used = 0;
        } else {
            if (used == sizeof(line) - 1)
                goto done;
            line[used++] = (char)ch;
        }
    }
    if (ferror(stream))
        goto done;
    if (used != 0) {
        line[used] = '\0';
        if (++lines > 256 || !check_line(line, expected, count, &matched))
            goto done;
    }
    good = matched == count;
done:
    if (fclose(stream) != 0)
        good = 0;
    return good;
}

PAM_EXTERN int pam_sm_authenticate(pam_handle_t *pamh, int flags,
                                 int argc, const char **argv)
{
    const char *token = NULL;
    (void)flags;
    (void)argv;
    if (argc != 0 ||
        pam_get_authtok(pamh, PAM_AUTHTOK, &token, NULL) != PAM_SUCCESS ||
        token == NULL || token[0] != '\0')
        return PAM_IGNORE;
    if (!auth_shape(GOODIX_GATE_VENDOR_PATH, login_auth,
                    sizeof(login_auth) / sizeof(login_auth[0])) ||
        !auth_shape(GOODIX_GATE_PASSWORD_PATH, password_auth,
                    sizeof(password_auth) / sizeof(password_auth[0])) ||
        !auth_shape(GOODIX_GATE_POSTLOGIN_PATH, NULL, 0))
        return PAM_IGNORE;
    return PAM_SUCCESS;
}

PAM_EXTERN int pam_sm_setcred(pam_handle_t *pamh, int flags,
                            int argc, const char **argv)
{
    (void)pamh;
    (void)flags;
    (void)argc;
    (void)argv;
    return PAM_IGNORE;
}
