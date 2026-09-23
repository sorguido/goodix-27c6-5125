/* SPDX-License-Identifier: GPL-2.0-or-later */
/* VM-only unit test: fake tokens and temporary PAM-text fixtures; no PAM login. */
#define _POSIX_C_SOURCE 200809L
#include <security/pam_modules.h>
#include <security/pam_ext.h>

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static char vendor_path[512], password_path[512], postlogin_path[512];
static const char *fake_token = "";
static int fake_result = PAM_SUCCESS, token_calls, open_calls;
static int fail_open, fail_read, read_failed, fail_close;
static unsigned int tests;

int pam_get_authtok(pam_handle_t *pamh, int item, const char **token,
                   const char *prompt)
{
    (void)pamh;
    if (item != PAM_AUTHTOK || prompt != NULL)
        abort();
    ++token_calls;
    *token = fake_token;
    return fake_result;
}

static int fixture_open(const char *path, int flags)
{
    ++open_calls;
    if (fail_open) {
        errno = EACCES;
        return -1;
    }
    return open(path, flags);
}

static int fixture_getc(FILE *stream)
{
    if (fail_read) {
        read_failed = 1;
        return EOF;
    }
    return fgetc(stream);
}

static int fixture_error(FILE *stream)
{
    return read_failed || ferror(stream);
}

static int fixture_close(FILE *stream)
{
    int result = fclose(stream);
    return fail_close ? EOF : result;
}

#define GOODIX_GATE_TEST 1
#define GOODIX_GATE_VENDOR_PATH vendor_path
#define GOODIX_GATE_PASSWORD_PATH password_path
#define GOODIX_GATE_POSTLOGIN_PATH postlogin_path
#define open fixture_open
#define fgetc fixture_getc
#define ferror fixture_error
#define fclose fixture_close
#include "pam_goodix_login_gate.c"
#undef open
#undef fgetc
#undef ferror
#undef fclose

static const char baseline_vendor[] =
    "#%PAM-1.0\n"
    "auth [success=done ignore=ignore default=bad] pam_selinux_permit.so\n"
    "auth substack password-auth\n"
    "-auth optional pam_gnome_keyring.so\n"
    "-auth optional pam_kwallet5.so\n"
    "-auth optional pam_kwallet.so\n"
    "-auth optional pam_oo7.so\n"
    "auth include postlogin\n"
    "account required pam_nologin.so\n"
    "session include password-auth\n";
static const char baseline_password[] =
    "auth required pam_env.so\n"
    "auth required pam_faildelay.so delay=2000000\n"
    "auth sufficient pam_unix.so nullok\n"
    "auth required pam_deny.so\n";
static const char baseline_postlogin[] =
    "# Generated configuration\n\n"
    "session optional pam_umask.so silent\n";

static void write_bytes(const char *path, const char *bytes, size_t length,
                        const char *mode)
{
    FILE *stream = fopen(path, mode);
    if (stream == NULL || fwrite(bytes, 1, length, stream) != length ||
        fclose(stream) != 0) {
        fputs("fixture write failed\n", stderr);
        exit(1);
    }
}

static void write_text(const char *path, const char *text, const char *mode)
{
    write_bytes(path, text, strlen(text), mode);
}

static void reset(void)
{
    write_text(vendor_path, baseline_vendor, "w");
    write_text(password_path, baseline_password, "w");
    write_text(postlogin_path, baseline_postlogin, "w");
    fake_token = "";
    fake_result = PAM_SUCCESS;
    token_calls = open_calls = 0;
    fail_open = fail_read = read_failed = fail_close = 0;
}

static void expect(const char *name, int expected, int expected_opens)
{
    int result = pam_sm_authenticate(NULL, 0, 0, NULL);
    if (result != expected || token_calls != 1 ||
        (expected_opens >= 0 && open_calls != expected_opens)) {
        fprintf(stderr, "FAIL %s: result=%d token_calls=%d opens=%d\n",
                name, result, token_calls, open_calls);
        exit(1);
    }
    ++tests;
}

int main(void)
{
    char directory[] = "/tmp/goodix-login-gate-XXXXXX";
    char oversized[1024];
    const char embedded_nul[] = "# comment\0auth required pam_deny.so\n";
    const int errors[] = {PAM_SYSTEM_ERR, PAM_BUF_ERR, PAM_CONV_ERR,
                          PAM_AUTH_ERR, PAM_AUTHTOK_ERR, PAM_INCOMPLETE,
                          PAM_IGNORE};
    size_t i;

    if (mkdtemp(directory) == NULL)
        return 1;
    if (snprintf(vendor_path, sizeof(vendor_path), "%s/plasmalogin", directory) < 0 ||
        snprintf(password_path, sizeof(password_path), "%s/password-auth", directory) < 0 ||
        snprintf(postlogin_path, sizeof(postlogin_path), "%s/postlogin", directory) < 0)
        return 1;

    reset();
    expect("explicit empty token and known auth policy", PAM_SUCCESS, 3);
    reset();
    fake_token = "synthetic-password";
    fail_open = 1;
    expect("password never inspects configuration", PAM_IGNORE, 0);
    reset();
    fake_token = " ";
    expect("space is a password, not an empty token", PAM_IGNORE, 0);
    reset();
    fake_token = NULL;
    expect("successful NULL response is not opt-in", PAM_IGNORE, 0);
    for (i = 0; i < sizeof(errors) / sizeof(errors[0]); ++i) {
        reset();
        fake_result = errors[i];
        expect("PAM API error never selects fingerprint", PAM_IGNORE, 0);
    }
    reset();
    if (pam_sm_authenticate(NULL, 0, 1, NULL) != PAM_IGNORE ||
        token_calls != 0 || open_calls != 0)
        return 1;
    ++tests;
    reset();
    fail_open = 1;
    expect("open error", PAM_IGNORE, 1);
    reset();
    fail_read = 1;
    expect("read error", PAM_IGNORE, 1);
    reset();
    fail_close = 1;
    expect("close error", PAM_IGNORE, 1);
    reset();
    if (unlink(vendor_path) != 0)
        return 1;
    expect("missing vendor file", PAM_IGNORE, 1);
    reset();
    if (unlink(postlogin_path) != 0)
        return 1;
    expect("missing included policy", PAM_IGNORE, 3);
    reset();
    write_text(vendor_path, "auth required pam_deny.so\n", "a");
    expect("new vendor auth policy", PAM_IGNORE, 1);
    reset();
    write_text(password_path, "auth required pam_faillock.so preauth\n", "a");
    expect("new credential policy cannot be bypassed", PAM_IGNORE, 2);
    reset();
    write_text(postlogin_path, "auth required pam_deny.so\n", "a");
    expect("new postlogin auth policy cannot be bypassed", PAM_IGNORE, 3);
    reset();
    write_text(vendor_path, "auth substack password-auth\n", "w");
    expect("missing auth rows", PAM_IGNORE, 1);
    reset();
    write_text(password_path,
               "auth required pam_deny.so\nauth sufficient pam_unix.so nullok\n",
               "w");
    expect("reordered auth policy", PAM_IGNORE, 2);
    reset();
    write_text(vendor_path, "account required pam_new_account_policy.so\n"
                            "session required pam_new_session_policy.so\n", "a");
    expect("current account and session policy is delegated", PAM_SUCCESS, 3);
    reset();
    write_text(password_path,
               " \t# comment\n\n"
               "  auth\t required  pam_env.so \t\n"
               "auth required pam_faildelay.so delay=2000000\n"
               "auth sufficient pam_unix.so nullok\n"
               "auth required pam_deny.so", "w");
    expect("ASCII spacing, comments and no final newline", PAM_SUCCESS, 3);
    reset();
    write_text(vendor_path, "# comment ending in continuation \\\n", "w");
    write_text(vendor_path, baseline_vendor, "a");
    expect("comment continuation ambiguity", PAM_IGNORE, 1);
    reset();
    write_text(postlogin_path, "session optional \\\npam_umask.so\n", "a");
    expect("continued policy is not interpreted", PAM_IGNORE, 3);
    reset();
    write_bytes(postlogin_path, embedded_nul, sizeof(embedded_nul) - 1, "a");
    expect("embedded NUL", PAM_IGNORE, 3);
    reset();
    write_text(postlogin_path, "@include unknown\n", "a");
    expect("unknown policy syntax", PAM_IGNORE, 3);
    reset();
    memset(oversized, 'x', sizeof(oversized));
    write_bytes(postlogin_path, oversized, sizeof(oversized), "a");
    expect("oversized line", PAM_IGNORE, 3);
    reset();
    for (i = 0; i < 257; ++i)
        write_text(postlogin_path, "# comment\n", "a");
    expect("too many rows", PAM_IGNORE, 3);
    reset();
    for (i = 0; i < 65; ++i)
        write_bytes(postlogin_path, oversized, sizeof(oversized), "a");
    expect("oversized file", PAM_IGNORE, 3);
    reset();
    if (unlink(postlogin_path) != 0 || mkfifo(postlogin_path, 0600) != 0)
        return 1;
    expect("non-regular policy path", PAM_IGNORE, 3);
    if (unlink(postlogin_path) != 0)
        return 1;
    reset();
    if (pam_sm_setcred(NULL, PAM_ESTABLISH_CRED, 0, NULL) != PAM_IGNORE ||
        token_calls != 0 || open_calls != 0)
        return 1;
    ++tests;

    if (unlink(vendor_path) != 0 || unlink(password_path) != 0 ||
        unlink(postlogin_path) != 0 || rmdir(directory) != 0)
        return 1;
    printf("GATE_UNIT_TESTS=PASS cases=%u (synthetic tokens, no PAM login)\n", tests);
    return 0;
}
