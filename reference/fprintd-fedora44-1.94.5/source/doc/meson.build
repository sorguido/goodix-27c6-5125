subdir('dbus')

version_file = configure_file(
    input: 'version.xml.in',
    output: 'version.xml',
    configuration: configuration_data({
        'VERSION': meson.project_version(),
    }),
)

gnome.gtkdoc(meson.project_name(),
    main_xml: 'fprintd-docs.xml',
    src_dir: meson.source_root() / 'src',
    dependencies: [
        declare_dependency(
            sources: dbus_interfaces_refs,
            link_with: libfprintd_private,
        ),
    ],
    content_files: [
        version_file,
        dbus_interfaces_refs,
    ],
    ignore_headers: [
        'config.h',
    ],
    install: true)
