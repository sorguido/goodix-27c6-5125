# Meson doesn't allow to have configure_file's as targets we depend on... Meh!
pam_service_file = custom_target('pam_test_service_file',
    output: 'null',
    command: 'true',
    depends: pam_fprintd,
    depend_files: configure_file(
        input: 'fprintd-pam-test.in',
        output: 'fprintd-pam-test',
        configuration: configuration_data({
            'FPRINTDPAMPATH': pam_fprintd.full_path(),
        }),
    ),
)
