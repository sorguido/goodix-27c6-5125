#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
Minimal host-only replacement for glib-mkenums.

Parses a small subset of C enum declarations and emits the GEnum/GFlags
registration boilerplate needed to link the repository-local libfprint copy
when glib-mkenums is not available in the build environment.
"""
import argparse
import re
import sys


def camel_to_upper_snake(name: str, prefix: str) -> str:
    """Strip identifier prefix and convert CamelCase to UPPER_SNAKE."""
    if name.startswith(prefix):
        name = name[len(prefix):]
    name = re.sub(r'([^A-Z])([A-Z])', r'\1_\2', name)
    return name.upper()


def simple_nick(value_name: str) -> str:
    """Use a stable lower-case representation as the value nick."""
    return value_name.lower().replace('_', '-')


def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    name = re.sub(r'([^A-Z])([A-Z])', r'\1_\2', name)
    name = re.sub(r'([A-Z])([A-Z][a-z])', r'\1_\2', name)
    return name.lower()


def parse_enum_blocks(text: str):
    """Yield (enum_name, is_flags, [(value_name, value_expr)]) tuples."""
    # Strip C comments.
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'//[^\n]*', '', text)

    pattern = re.compile(
        r'typedef\s+enum\s*(?:<[^>]*>)?\s*\{(.*?)\}\s*([A-Za-z_]\w*)\s*;',
        re.DOTALL,
    )

    for match in pattern.finditer(text):
        body = match.group(1)
        enum_name = match.group(2)
        values = []
        is_flags = False

        # Split on commas, ignoring commas inside parenthesised expressions.
        depth = 0
        current = []
        for ch in body:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == ',' and depth == 0:
                if current:
                    values.append(''.join(current).strip())
                    current = []
                continue
            current.append(ch)
        if current:
            values.append(''.join(current).strip())

        parsed = []
        for entry in values:
            entry = entry.strip()
            if not entry:
                continue
            if '=' in entry:
                name, expr = entry.split('=', 1)
                name = name.strip()
                expr = expr.strip()
            else:
                name = entry
                expr = None
            if '<<' in (expr or ''):
                is_flags = True
            parsed.append((name, expr))

        yield enum_name, is_flags, parsed


def generate_header(input_paths, identifier_prefix, symbol_prefix, header_guard):
    lines = [
        f'#ifndef {header_guard}',
        f'#define {header_guard}',
        '#include <glib-object.h>',
        'G_BEGIN_DECLS',
        '',
    ]

    macro_prefix = identifier_prefix.upper()

    for path in input_paths:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        for enum_name, _is_flags, _values in parse_enum_blocks(text):
            short = camel_to_upper_snake(enum_name, identifier_prefix)
            func = f'{symbol_prefix}_{camel_to_snake(enum_name[len(identifier_prefix):])}_get_type'
            lines.append(f'GType {func} (void) G_GNUC_CONST;')
            lines.append(f'#define {macro_prefix}_TYPE_{short} ({func} ())')
            lines.append('')

    lines.extend([
        'G_END_DECLS',
        f'#endif /* {header_guard} */',
        '',
    ])
    return '\n'.join(lines)


def generate_source(input_paths, identifier_prefix, symbol_prefix, header_name):
    import os

    lines = [f'#include "{header_name}"', '']

    for path in input_paths:
        lines.append(f'#include "{os.path.basename(path)}"')
    lines.append('')

    for path in input_paths:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        for enum_name, is_flags, values in parse_enum_blocks(text):
            func = f'{symbol_prefix}_{camel_to_snake(enum_name[len(identifier_prefix):])}_get_type'
            type_name = enum_name
            value_type = 'GFlagsValue' if is_flags else 'GEnumValue'
            register_func = 'g_flags_register_static' if is_flags else 'g_enum_register_static'

            lines.append(f'GType {func} (void)')
            lines.append('{')
            lines.append('  static gsize gtype_id = 0;')
            lines.append(f'  static const {value_type} values[] = {{')

            for value_name, expr in values:
                if expr is None:
                    expr_text = value_name
                else:
                    expr_text = expr
                nick = simple_nick(value_name)
                lines.append(f'    {{ {expr_text}, "{value_name}", "{nick}" }},')

            lines.append('    { 0, NULL, NULL }')
            lines.append('  };')
            lines.append('  if (g_once_init_enter (&gtype_id))')
            lines.append('    {')
            lines.append(f'      GType new_type = {register_func} ("{type_name}", values);')
            lines.append('      g_once_init_leave (&gtype_id, new_type);')
            lines.append('    }')
            lines.append('  return (GType) gtype_id;')
            lines.append('}')
            lines.append('')

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Generate libfprint enum registration.')
    parser.add_argument('--identifier-prefix', required=True)
    parser.add_argument('--symbol-prefix', required=True)
    parser.add_argument('--header-guard', required=True)
    parser.add_argument('--header-name', required=True)
    parser.add_argument('--output-header', required=True)
    parser.add_argument('--output-source', required=True)
    parser.add_argument('input', nargs='+')
    args = parser.parse_args()

    header = generate_header(args.input, args.identifier_prefix, args.symbol_prefix, args.header_guard)
    source = generate_source(args.input, args.identifier_prefix, args.symbol_prefix, args.header_name)

    with open(args.output_header, 'w', encoding='utf-8') as f:
        f.write('/* Generated by generate_libfprint_enums.py */\n')
        f.write(header)
    with open(args.output_source, 'w', encoding='utf-8') as f:
        f.write('/* Generated by generate_libfprint_enums.py */\n')
        f.write(source)


if __name__ == '__main__':
    main()
