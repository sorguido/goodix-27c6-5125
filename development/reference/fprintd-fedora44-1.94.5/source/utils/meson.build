libfprintd_utils_dep = declare_dependency(
    include_directories: [
        include_directories('../src'),
        include_directories('../pam'),
    ],
    dependencies: [
        glib_dep,
        gio_dep,
        gio_unix_dep,
    ],
    sources: [
        fprintd_dbus_sources,
    ],
    link_with: [
        libfprintd_private
    ],
)

utils = [
    'delete',
    'enroll',
    'list',
    'verify',
]

fprintd_utils = []

foreach util: utils
    fprintd_utils += executable('fprintd-' + util,
        sources: util + '.c',
        dependencies: libfprintd_utils_dep,
        install: true,
    )
endforeach
