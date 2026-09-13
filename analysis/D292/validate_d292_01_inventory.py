#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate D292/01 production inputs, delta and exported symbol surface."""

from __future__ import annotations

import json
import posixpath
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "analysis/D292/D292_01_PRODUCTION_FILE_SET.json"
MESON = ROOT / "reference/libfprint-fedora44-1.94.100/source/libfprint/meson.build"
BUILDER = ROOT / "production/build-inner.sh"
FEDORA_PROVENANCE = ROOT / "reference/libfprint-fedora44-1.94.100/PROVENANCE.md"
LICENSING_LEDGER = ROOT / "docs/LICENSING_AND_PROVENANCE.md"
DEVICE_HEADER = ROOT / "libfprint-driver/goodix_fpimage_device.h"
DEVICE_SOURCE = ROOT / "libfprint-driver/goodix_fpimage_device.c"
DOWNSTREAM_PATHS = ROOT / "production/downstream-paths.txt"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"D292_01_INVENTORY_CHECK=FAIL reason={message}")


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    require(result.returncode == 0, "git_failed:" + "_".join(args))
    return result.stdout


def array_sources(text: str, name: str) -> set[str]:
    match = re.search(rf"^{re.escape(name)}\s*=\s*\[(.*?)^\]", text,
                      flags=re.MULTILINE | re.DOTALL)
    require(match is not None, f"meson_array_missing:{name}")
    return set(re.findall(r"'([^']+\.(?:c|cpp))'", match.group(1)))


def repo_core_paths(names: set[str]) -> set[str]:
    prefix = "reference/libfprint-fedora44-1.94.100/source/libfprint/"
    return {prefix + name for name in names}


def goodix_sources(text: str) -> set[str]:
    match = re.search(
        r"'goodix_27c6_5125'\s*:\s*files\((.*?)^\s*\),", text,
        flags=re.MULTILINE | re.DOTALL,
    )
    require(match is not None, "meson_goodix_source_block_missing")
    raw = re.findall(r"'([^']+\.(?:c|cpp))'", match.group(1))
    base = "reference/libfprint-fedora44-1.94.100/source/libfprint"
    return {posixpath.normpath(posixpath.join(base, path)) for path in raw}


def license_notice_ok(path: Path, license_name: str) -> bool:
    text = path.read_text(errors="replace")[:4096]
    if license_name == "LGPL-2.1-or-later":
        return "LGPL-2.1-or-later" in text or "GNU Lesser General Public" in text
    if license_name == "LGPL-2.0-or-later":
        return "GNU Library General Public" in text
    if license_name == "GPL-2.0-or-later":
        return "GPL-2.0-or-later" in text and "LGPL-2.1-or-later" not in text
    if license_name == "NIST-PD":
        return "public domain" in text and "National Institute" in text
    return False


def without_test_seams(text: str) -> str:
    output: list[str] = []
    depth = 0
    for line in text.splitlines(keepends=True):
        if (re.match(r"\s*#\s*ifdef\s+GOODIX_ENABLE_TEST_SEAMS\b", line) or
                (re.match(r"\s*#\s*if\b", line) and
                 "GOODIX_ENABLE_TEST_SEAMS" in line)):
            depth += 1
            continue
        if depth:
            if re.match(r"\s*#\s*if", line):
                depth += 1
            elif re.match(r"\s*#\s*endif", line):
                depth -= 1
            continue
        output.append(line)
    require(depth == 0, "unterminated_test_seam_guard")
    return "".join(output)


def remove_comments_and_strings(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", " ", text)
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
    text = re.sub(r"'(?:\\.|[^'\\])*'", "''", text)
    return text


def explicit_prototypes(text: str) -> set[str]:
    text = remove_comments_and_strings(text)
    return set(re.findall(
        r"\b((?:goodix_[A-Za-z0-9_]+|fpi_device_goodix_27c6_5125_get_type))"
        r"\s*\([^;{}]*\)\s*(?:G_GNUC_CONST\s*)?;",
        text, flags=re.DOTALL,
    ))


def section_prototypes(header: str, label: str) -> set[str]:
    marker = f"/* --- {label} --- */"
    require(marker in header, "header_section_missing:" + label)
    body = header.split(marker, 1)[1]
    ends = [value for value in (body.find("/* ---"), body.find("G_END_DECLS"))
            if value >= 0]
    require(ends, "header_section_unterminated:" + label)
    return explicit_prototypes(body[:min(ends)])


def symbol_call_classes(symbol: str, production_paths: set[str]) -> set[str]:
    pattern = re.compile(r"\b" + re.escape(symbol) + r"\s*\(")
    classes: set[str] = set()
    source = remove_comments_and_strings(DEVICE_SOURCE.read_text(errors="replace"))
    if len(pattern.findall(source)) > 1:
        classes.add("production_internal")
    for relative in git("ls-files", "*.c", "*.cpp").splitlines():
        if relative == "libfprint-driver/goodix_fpimage_device.c":
            continue
        text = remove_comments_and_strings((ROOT / relative).read_text(errors="replace"))
        if not pattern.search(text):
            continue
        if "/tests/" in relative or relative.startswith("tests/"):
            classes.add("tests")
        elif relative.startswith("tools/"):
            classes.add("host_tooling")
        elif relative.startswith("operator_kit/"):
            classes.add("operator_tooling")
        elif relative in production_paths:
            classes.add("production_other_tu")
        else:
            classes.add("unclassified:" + relative)
    if symbol == "fpi_device_goodix_27c6_5125_get_type":
        classes.add("generated_registry")
    return classes


def local_header_closure(starts: set[str]) -> set[str]:
    stack = [Path(path) for path in starts]
    seen: set[Path] = set()
    headers: set[str] = set()
    while stack:
        relative = stack.pop()
        if relative in seen:
            continue
        seen.add(relative)
        text = (ROOT / relative).read_text(errors="replace")
        for include in re.findall(r'^\s*#\s*include\s*"([^"]+)"', text,
                                  flags=re.MULTILINE):
            candidates = (
                relative.parent / include,
                Path("libfprint-driver") / include,
                Path("reference/libfprint-fedora44-1.94.100/source/libfprint") / include,
                Path("Rockytkg/libfprint/libfprint/sigfm") / include,
            )
            resolved = next((path for path in candidates if (ROOT / path).is_file()), None)
            if resolved is None or resolved in seen:
                continue
            stack.append(resolved)
            path_text = resolved.as_posix()
            if (path_text.startswith("libfprint-driver/") or
                    path_text.startswith("Rockytkg/")) and resolved.suffix in {".h", ".hpp"}:
                headers.add(path_text)
    return headers


def main() -> None:
    data = json.loads(INVENTORY.read_text())
    require(data["d292_02_task_baseline"] ==
            "0bda0dc239cad9c5d62cbb906f1c1fc7183c753b",
            "d292_02_task_baseline_mismatch")
    require(data["d292_01_inventory_baseline"] ==
            "420894d093c04b2dc31980cf9292389362dfc6f0",
            "d292_01_inventory_baseline_mismatch")
    require("Fedora KDE" in data["target"] and "APP12509" in data["target"],
            "target_mismatch")
    meson_text = MESON.read_text()
    groups = data["translation_unit_groups"]
    require(len({group["id"] for group in groups}) == len(groups), "duplicate_group_id")
    manifest_by_meson: dict[str, set[str]] = {}
    all_paths: list[str] = []
    for group in groups:
        require(group["license"] and group["provenance"] and group["origin"],
                f"missing_mapping:{group['id']}")
        paths = group["paths"]
        require(paths and len(paths) == len(set(paths)), f"empty_or_duplicate_group:{group['id']}")
        manifest_by_meson.setdefault(group["meson_group"], set()).update(paths)
        for relative in paths:
            path = ROOT / relative
            require(path.is_file(), f"source_missing:{relative}")
            require(license_notice_ok(path, group["license"]), f"license_notice_mismatch:{relative}")
            all_paths.append(relative)
    require(len(all_paths) == len(set(all_paths)), "translation_unit_duplicated")
    require(manifest_by_meson["libfprint_sources"] == repo_core_paths(array_sources(meson_text, "libfprint_sources")), "public_core_differs_from_meson")
    require(manifest_by_meson["libfprint_private_sources"] == repo_core_paths(array_sources(meson_text, "libfprint_private_sources")), "private_core_differs_from_meson")
    require(manifest_by_meson["nbis_sources"] == repo_core_paths(array_sources(meson_text, "nbis_sources")), "nbis_differs_from_meson")
    require(manifest_by_meson["goodix_27c6_5125"] == goodix_sources(meson_text), "goodix_driver_differs_from_meson")
    forbidden = ("analysis/", "operator_kit/", "tests/")
    compiled_forbidden = [path for path in all_paths if path.startswith(forbidden) or "/tests/" in path]
    require(not compiled_forbidden, "compiled_source_under_nonproduction_surface")

    generated = data["generated_translation_units"]
    require({item["path"] for item in generated} == {"@BUILD@/libfprint/fp-enums.c", "@BUILD@/libfprint/fpi-enums.c", "@BUILD@/libfprint/fpi-drivers.c"}, "generated_translation_unit_set_mismatch")
    for item in generated:
        require(item["generator"] and item["license"] and item["provenance"], f"generated_mapping_missing:{item['path']}")

    delta = data["documented_downstream_delta"]
    delta_manifest = set(delta["build_files"]) | set(delta["modified_core_files"]) | set(delta["test_only_files"])
    delta_actual = set(git("diff", "--name-only", delta["pristine_baseline"], "--", "reference/libfprint-fedora44-1.94.100/source").splitlines())
    require(delta_manifest == delta_actual, "downstream_delta_diff_mismatch")
    require(not (set(delta["build_files"]) & set(delta["modified_core_files"])) and not (set(delta["test_only_files"]) & (set(delta["build_files"]) | set(delta["modified_core_files"]))), "downstream_delta_categories_overlap")
    require(delta["test_only_files"] == ["reference/libfprint-fedora44-1.94.100/source/tests/meson.build"], "test_only_downstream_delta_mismatch")
    production_delta = delta_actual - set(delta["test_only_files"])
    downstream_lines = DOWNSTREAM_PATHS.read_text().splitlines()
    require(len(downstream_lines) == len(set(downstream_lines)) == 15,
            "downstream_path_count_or_duplicate")
    require(set(downstream_lines) == production_delta ==
            set(delta["build_files"]) | set(delta["modified_core_files"]),
            "downstream_path_set_mismatch")
    for relative in delta_manifest:
        require((ROOT / relative).is_file(), f"delta_path_missing:{relative}")
    provenance_text = FEDORA_PROVENANCE.read_text() + LICENSING_LEDGER.read_text()
    require("libfprint 1.94.100" in provenance_text and delta["license"], "downstream_provenance_or_license_missing")

    non_tu = data["production_non_tu_inputs"]
    baseline_tree = non_tu["fedora_source_tree_baseline"]
    require((ROOT / baseline_tree["path"]).is_dir(), "fedora_baseline_tree_missing")
    require(baseline_tree["pristine_commit"] == delta["pristine_baseline"], "fedora_baseline_anchor_mismatch")
    git("cat-file", "-e", baseline_tree["pristine_commit"] + "^{commit}")
    for key in ("local_driver_headers", "rockytkg_sigfm_headers", "current_build_orchestration_inputs"):
        require(len(non_tu[key]) == len(set(non_tu[key])), "duplicate_non_tu:" + key)
        for relative in non_tu[key]:
            require((ROOT / relative).exists(), "non_tu_input_missing:" + relative)
    local_headers = set(non_tu["local_driver_headers"]) | set(non_tu["rockytkg_sigfm_headers"])
    require(local_headers == local_header_closure(manifest_by_meson["goodix_27c6_5125"]), "local_header_closure_mismatch")

    surface = data["external_symbol_surface"]
    header_text = DEVICE_HEADER.read_text()
    explicit = explicit_prototypes(without_test_seams(header_text))
    category_keys = ("registry_runtime_production", "shared_internal_production", "potentially_mixed_or_ambiguous")
    categories = set().union(*(set(surface[key]) for key in category_keys))
    require(explicit == categories, "unprotected_explicit_symbol_inventory_mismatch")
    require(sum(len(surface[key]) for key in category_keys) == len(categories), "external_symbol_categories_overlap")
    newly_guarded = set(surface["test_or_host_only_guarded"])
    preexisting_guarded = set(surface["preexisting_guarded_test_seams"])
    guarded = newly_guarded | preexisting_guarded
    all_header_explicit = explicit_prototypes(header_text)
    require(all_header_explicit == explicit | guarded,
            "guarded_explicit_symbol_inventory_mismatch")
    require(not (explicit & guarded), "guarded_and_production_symbol_overlap")
    source_text = remove_comments_and_strings(DEVICE_SOURCE.read_text())
    for symbol in explicit:
        require(re.search(r"\b" + re.escape(symbol) + r"\s*\([^;{}]*\)\s*\{", source_text, flags=re.DOTALL) is not None, "external_symbol_definition_missing:" + symbol)
        expected = set().union(*(set(surface[key].get(symbol, [])) for key in category_keys))
        actual = symbol_call_classes(symbol, set(all_paths))
        require(expected == actual, "call_site_class_mismatch:" + symbol + ":" + ",".join(sorted(actual)))
    source_without_seams = remove_comments_and_strings(
        without_test_seams(DEVICE_SOURCE.read_text()))
    guarded_classes = (surface["test_or_host_only_guarded"] |
                       surface["preexisting_guarded_test_seams"])
    for symbol, expected_classes in guarded_classes.items():
        require(re.search(r"\b" + re.escape(symbol) + r"\s*\([^;{}]*\)\s*\{",
                          source_text, flags=re.DOTALL) is not None,
                "guarded_symbol_definition_missing:" + symbol)
        require(re.search(r"\b" + re.escape(symbol) + r"\s*\([^;{}]*\)\s*\{",
                          source_without_seams, flags=re.DOTALL) is None,
                "guarded_symbol_definition_leaks_production:" + symbol)
        require(set(expected_classes) == symbol_call_classes(symbol, set(all_paths)),
                "guarded_call_site_class_mismatch:" + symbol)
    test_only_production_calls = {symbol: sorted(symbol_call_classes(symbol, set(all_paths))) for symbol in guarded if symbol_call_classes(symbol, set(all_paths)) & {"production_internal", "production_other_tu", "generated_registry"}}
    require(not test_only_production_calls, "test_only_symbol_has_production_call_site")
    for label, expected in surface["header_labeled_sections"].items():
        require(section_prototypes(header_text, label) == set(expected), "header_labeled_section_changed:" + label)
    raw_source = DEVICE_SOURCE.read_text()
    require("G_DECLARE_DERIVABLE_TYPE (GoodixFpImageDevice" in header_text and "G_DEFINE_TYPE_WITH_PRIVATE (GoodixFpImageDevice" in raw_source and "G_DEFINE_TYPE (GoodixUsbFpImageDevice" in raw_source, "macro_generated_type_surface_changed")
    require(set(surface["macro_generated_external"]) == {"goodix_fpimage_device_get_type", "goodix_usb_fpimage_device_get_type"}, "macro_generated_symbol_inventory_mismatch")

    for dependency in data["current_build_pipeline_dependencies"]:
        if "path" in dependency:
            require((ROOT / dependency["path"]).exists(), f"build_dependency_missing:{dependency['path']}")
    builder_text = BUILDER.read_text()
    require("-Ddrivers=goodix_27c6_5125" in builder_text, "target_driver_option_missing")
    require("-DGOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE" in builder_text,
            "stable_production_flag_missing")
    require("GOODIX_D282_DIRECT_ENROLL_PROFILE" not in builder_text,
            "historical_production_flag_present")
    require("GOODIX_ENABLE_TEST_SEAMS" not in builder_text, "test_seams_enabled_by_builder")
    require("GOODIX_LIBFPRINT_SIGFM" in meson_text, "sigfm_define_missing_from_meson")
    test_area_build_dependencies = [item["path"] for item in data["current_build_pipeline_dependencies"] if "path" in item and "/tests/" in item["path"]]
    require(not test_area_build_dependencies, "test_area_build_dependency_present")

    print("D292_01_INVENTORY_CHECK=PASS")
    print(f"D292_01_COMPILED_TRANSLATION_UNIT_COUNT={len(all_paths)}")
    print(f"D292_01_GENERATED_TRANSLATION_UNIT_COUNT={len(generated)}")
    print(f"D292_01_LOCAL_AND_ROCKY_HEADER_INPUT_COUNT={len(local_headers)}")
    print(f"D292_01_DOWNSTREAM_DELTA_COUNT={len(delta_actual)}")
    print(f"D292_01_DOWNSTREAM_PRODUCTION_BUILD_INPUT_COUNT={len(delta['build_files'])}")
    print(f"D292_01_DOWNSTREAM_PRODUCTION_CORE_COUNT={len(delta['modified_core_files'])}")
    print(f"D292_01_DOWNSTREAM_TEST_ONLY_COUNT={len(delta['test_only_files'])}")
    print(f"D292_02_PRODUCT_PATCH_PATH_COUNT={len(downstream_lines)}")
    print(f"D292_01_UNPROTECTED_EXPLICIT_SYMBOL_COUNT={len(explicit)}")
    print(f"D292_01_REGISTRY_RUNTIME_SYMBOL_COUNT={len(surface['registry_runtime_production'])}")
    print(f"D292_01_SHARED_INTERNAL_PRODUCTION_SYMBOL_COUNT={len(surface['shared_internal_production'])}")
    print(f"D292_02_NEWLY_GUARDED_TEST_HOST_ONLY_SYMBOL_COUNT={len(newly_guarded)}")
    print(f"D292_02_TOTAL_TEST_SEAM_SYMBOL_COUNT={len(guarded)}")
    print(f"D292_01_AMBIGUOUS_SYMBOL_COUNT={len(surface['potentially_mixed_or_ambiguous'])}")
    print("D292_01_TEST_HOST_ONLY_PRODUCTION_CALL_SITE_COUNT=0")
    print(f"D292_01_HEADER_LABELED_SYMBOL_COUNT={sum(len(v) for v in surface['header_labeled_sections'].values())}")
    print("D292_01_PRODUCTION_COMPILED_FORBIDDEN_PREFIX_COUNT=0")
    print(f"D292_02_BUILD_TEST_AREA_DEPENDENCY_COUNT={len(test_area_build_dependencies)}")
    print("D292_01_GOODIX_ENABLE_TEST_SEAMS=false")
    print("D292_02_PRODUCTION_FLAG=GOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE")
    print("D292_01_TARGET=FEDORA_KDE_APP12509")


if __name__ == "__main__":
    main()
