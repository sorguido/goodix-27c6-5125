/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Offline only: load Fedora OpenCV, never libfprint/fprintd or the reader.
 * Interpose just the huge-page fopen to simulate denial or the service's EOF.
 * This tests allocator behavior, not a real systemd mount or SELinux decision. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned probes;
static int empty_response;

FILE *fopen(const char *path, const char *mode)
{
    static FILE *(*real_fopen)(const char *, const char *);
    if (!real_fopen)
        real_fopen = dlsym(RTLD_NEXT, "fopen");
    if (!real_fopen)
        _Exit(10);
    if (strcmp(path, "/proc/sys/vm/nr_hugepages") == 0) {
        ++probes;
        if (strcmp(mode, "r") != 0)
            _Exit(11);
        if (empty_response)
            return real_fopen("/dev/null", mode);
        errno = EACCES;
        return NULL;
    }
    return real_fopen(path, mode);
}

int main(int argc, char **argv)
{
    if (argc != 2 || (strcmp(argv[1], "empty") && strcmp(argv[1], "denied")))
        return 1;
    empty_response = strcmp(argv[1], "empty") == 0;
    void *opencv = dlopen("libopencv_core.so.413", RTLD_NOW | RTLD_LOCAL);
    if (!opencv) {
        fprintf(stderr, "%s\n", dlerror());
        return 2;
    }
    printf("PROBES_AT_LIBRARY_LOAD=%u\n", probes);
    if (probes != 1)
        return 3;
    void *allocator = dlopen("libtbbmalloc.so.2", RTLD_NOW | RTLD_LOCAL);
    if (!allocator)
        return 4;
    void *(*allocate)(size_t) = dlsym(allocator, "scalable_malloc");
    void (*release)(void *) = dlsym(allocator, "scalable_free");
    if (!allocate || !release)
        return 5;
    for (unsigned i = 0; i < 100; ++i) {
        void *memory = allocate(4096);
        if (!memory)
            return 6;
        memset(memory, 0xa5, 4096);
        release(memory);
    }
    printf("PROBES_AFTER_100_ALLOCATIONS=%u\n", probes);
    return probes == 1 ? 0 : 7;
}
