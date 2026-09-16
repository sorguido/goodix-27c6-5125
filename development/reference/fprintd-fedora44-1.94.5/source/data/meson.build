install_data('net.reactivated.Fprint.conf',
    install_dir: dbus_conf_dir)

configure_file(
    configuration: configuration_data({
        'LIBEXECDIR': fprintd_installdir,
    }),
    input: 'net.reactivated.Fprint.service.in',
    output: 'net.reactivated.Fprint.service',
    install: true,
    install_dir: dbus_service_dir,
)

if get_option('systemd')
    configure_file(
        configuration: configuration_data({
            'libexecdir': fprintd_installdir,
        }),
        input: 'fprintd.service.in',
        output: 'fprintd.service',
        install: true,
        install_dir: systemd_unit_dir,
    )
endif

polkit_policy = 'net.reactivated.fprint.device.policy'
polkit_policy_target = i18n.merge_file(
    input: '@0@.in'.format(polkit_policy),
    output: polkit_policy,
    po_dir: meson.project_source_root() / 'po',
    install: true,
    install_dir: polkit_policy_directory,
)

if xmllint.found()
    test(polkit_policy,
        xmllint,
        depends: polkit_policy_target,
        args: [
            '--noout',
            polkit_policy_target.full_path(),
        ])
endif

install_data('fprintd.conf',
    install_dir: sysconfdir)

if get_option('man')
    manfiles = {
        'fprintd': 1,
        'pam_fprintd': 8,
    }

    foreach man_name, man_section: manfiles
        custom_target('man_' + man_name + '.' + man_section.to_string(),
            input: man_name + '.pod',
            output: man_name + '.' + man_section.to_string(),
            command: [
                pod2man,
                '-c', '',
                '-s', man_section.to_string(),
                '-q', 'none',
                '-n', man_name,
                '-r', 'freedesktop',
                '@INPUT@',
                '@OUTPUT@',
            ],
            install: true,
            install_dir: datadir / 'man' / 'man' + man_section.to_string(),
        )
    endforeach
endif
