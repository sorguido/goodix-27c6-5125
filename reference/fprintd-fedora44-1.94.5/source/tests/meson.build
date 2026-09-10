# Add a way to discover and run python unit tests separately
# https://github.com/mesonbuild/meson/issues/6851
python_tests = [
    # List all the python tests, must be in the form:
    # {
    #     'name': 'test name',
    #     'file': 'full test file path, use files('path')[0]',
    # Fields below are optional:
    #     'workdir': '',
    #     'env': [],
    #     'depends': [],
    #     'suite': [],
    #     'extra_args': [],
    #     'timeout': 30,
    #     'is_parallel': true,
    # }
]

address_sanitizer = get_option('b_sanitize') == 'address'

tests = [
    'fprintd',
    'test_fprintd_utils',
]

foreach t: tests
    python_tests += [
        {
            'name': t,
            'file': files(meson.current_source_dir() / t + '.py')[0],
            'env': [
                'G_DEBUG=fatal-criticals',
                'G_MESSAGES_DEBUG=all',
                'FPRINT_BUILD_DIR=' + meson.project_build_root() / 'src',
                'TOPSRCDIR=' + meson.project_source_root(),
            ],
            'depends': [
                fprintd,
                fprintd_utils,
            ],
            'suite': [t == 'fprintd' ? 'daemon' : ''],
        }
    ]
endforeach

if get_option('pam')
    subdir('pam')
endif

# Add a way to discover and run python unit tests separately
# https://github.com/mesonbuild/meson/issues/6851
unittest_inspector = find_program('unittest_inspector.py')

foreach pt: python_tests
    r = run_command(unittest_inspector, pt.get('file'), check: false)
    unit_tests = r.stdout().strip().split('\n')
    base_args = [ pt.get('file') ] + pt.get('extra_args', [])
    suite = pt.get('suite', [])

    if r.returncode() == 0 and unit_tests.length() > 0
        suite += pt.get('name')
    else
        unit_tests = [pt.get('name')]
    endif

    foreach ut: unit_tests
        ut_suite = suite
        ut_args = base_args
        if unit_tests.length() > 1
            ut_args += ut
            ut_suite += ut.split('.')[0]
        endif
        test(ut,
            python3,
            args: ut_args,
            suite: ut_suite,
            depends: pt.get('depends', []),
            workdir: pt.get('workdir', meson.project_build_root()),
            env: pt.get('env', []),
            timeout: pt.get('timeout', 30),
            is_parallel: pt.get('is_parallel', true),
        )
    endforeach
endforeach

timeout_multiplier = 1
test_envs = [
    'G_SLICE=always-malloc',
    'MALLOC_CHECK_=2',
]

if address_sanitizer
    lsan_suppress = files('LSAN-leaks-suppress.txt')[0]
    if meson.version().version_compare('>=1.4')
        lsan_suppress = lsan_suppress.full_path()
    else
        lsan_suppress = meson.project_source_root() / '@0@'.format(lsan_suppress)
    endif

    timeout_multiplier = 3
    test_envs += [
        'ADDRESS_SANITIZER=true',
        'ASAN_OPTIONS=@0@'.format(':'.join([
            'abort_on_error=true',
            'symbolize=true',
        ])),
        'LSAN_OPTIONS=@0@'.format(':'.join([
            'exitcode=0',
            'strict_string_checks=true',
            'suppressions=@0@'.format(lsan_suppress),
        ])),
    ]
endif

add_test_setup('default_setup',
    is_default: true,
    env: test_envs,
    timeout_multiplier: timeout_multiplier
)

if not address_sanitizer and find_program('valgrind', required: false).found()
    glib_share = glib_dep.get_variable('prefix') / 'share' / glib_dep.name()
    glib_suppressions = glib_share + '/valgrind/glib.supp'
    add_test_setup('valgrind',
        env: [
            'G_SLICE=always-malloc',
            'VALGRIND=' + glib_suppressions,
        ],
        timeout_multiplier: 5
    )
endif

