docbook_xml_header = custom_target('docbook_xml_header',
    output: 'docbook-xml-header.xml',
    command: [
        'echo', '-n',
        '<?xml version="1.0"?>\n',
        '<!DOCTYPE refentry PUBLIC "-//OASIS//DTD DocBook XML V4.1.2//EN" "http://www.oasis-open.org/docbook/xml/4.1.2/docbookx.dtd">\n',
    ],
    capture: true,
)

dbus_interfaces_refs = []
foreach interface_file: dbus_interfaces
    basename = run_command('basename', interface_file, '.xml', check: true).stdout().strip()
    dbus_interfaces_refs += custom_target(basename + '_ref',
        input: docbook_xml_header,
        output: basename + '.ref.xml',
        build_by_default: true,
        depend_files: interface_file,
        capture: true,
        command: [
            sh, '-c',
            'cat "$1"; "$2" "$3" "$4" | tail -n +2',
            '_', # argv0 ignored
            '@INPUT@',
            xsltproc, files('spec-to-docbook.xsl')[0], interface_file
        ],
    )
endforeach
