mapfile = files('pam_fprintd.ver')[0]
if meson.version().version_compare('>=1.4')
    mapfile_path = mapfile.full_path()
else
    mapfile_path = meson.project_source_root() / '@0@'.format(mapfile)
endif

pam_modules_dir = get_option('pam_modules_dir')
if pam_modules_dir == ''
    pam_modules_dir = get_option('prefix') / get_option('libdir') / 'security'
endif

pam_fprintd = shared_module('pam_fprintd',
    name_prefix: '',
    include_directories: [
        include_directories('..'),
    ],
    sources: [
        'pam_fprintd.c',
        'fingerprint-strings.h',
    ],
    dependencies: [
        libsystemd_dep,
        pam_dep,
        gettext_deps,
    ],
    c_args: [
        '-DLOCALEDIR="@0@"'.format(localedir),
        libsystemd_dep.name() == 'basu' ? ['-DFPRINTD_PAM_USE_BASU'] : [],
        has_openpam ? ['-DFPRINTD_PAM_USE_OPENPAM'] : [],
    ],
    link_args: [
        '-Wl,--version-script,@0@'.format(mapfile_path),
        '-Wl,--unresolved-symbols=report-all',
    ],
    link_depends: mapfile,
    install: true,
    install_dir: pam_modules_dir,
)
