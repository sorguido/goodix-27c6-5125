subdir('services')

tests = [
    'test_pam_fprintd',
]

preloaded_libs = []
pam_tests_ld_preload = []

if address_sanitizer
    # ASAN has to be the first in list
    preloaded_libs += 'asan'
endif

if pam_wrapper_dep.found()
    preloaded_libs += 'pam_wrapper'
endif

foreach libname: preloaded_libs
    lib = run_command(meson.get_compiler('c'),
        '-print-file-name=lib@0@.so'.format(libname),
        check: false,
    ).stdout().strip()

    # Support linker script files
    if run_command('grep', '-qI', '^INPUT', files(lib), check: false).returncode() == 0
        out = run_command('cat', lib).stdout()
        lib = out.split('(')[1].split(')')[0].strip()
    endif

    if lib != '' and lib[0] == '/'
        message('Found library @0@ as @1@'.format(libname, lib))
        preload_lib_path = files(lib)[0]
        if meson.version().version_compare('>=1.4')
            pam_tests_ld_preload += preload_lib_path.full_path()
        else
            pam_tests_ld_preload += '@0@'.format(preload_lib_path)
        endif
    else
        tests = []
        warning('No library found for ' + libname + ', skipping PAM tests')
    endif
endforeach

foreach t: tests
    python_tests += [
        {
            'name': t,
            'file': files(meson.current_source_dir() / t + '.py')[0],
            'is_parallel': false,
            'env': [
                'TOPBUILDDIR=' + meson.project_build_root(),
                'TOPSRCDIR=' + meson.project_source_root(),
                'LD_PRELOAD=' + ' '.join(pam_tests_ld_preload),
                'PAM_WRAPPER=1',
                'PAM_WRAPPER_DEBUGLEVEL=2',
                'PAM_WRAPPER_SERVICE_DIR=' + meson.current_build_dir() / 'services',
                'G_DEBUG=fatal-warnings',
            ],
            'depends': [
                pam_fprintd,
                pam_service_file,
            ],
            'suite': ['PAM'],
        }
    ]
endforeach
