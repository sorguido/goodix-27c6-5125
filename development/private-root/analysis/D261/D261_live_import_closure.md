# D261 bounded live-import closure

Derived from a fresh-process import of the supported D261 Python entrypoint and its bounded runtime modules. The operator shell is gated separately as `operator_kit/d261-live-fdt-arm-once.sh`.

`LIVE_IMPORT_CLOSURE_STATUS=PASS`  
`LIVE_IMPORT_CLOSURE_PATH_COUNT=16`  
`LIVE_IMPORT_CLOSURE_MISSING_PATH_COUNT=0`

| Path | Imported by | Execution role | Baseline gated |
| --- | --- | --- | --- |
| `core/__init__.py` | tools/d261_live_fdt_arm_once.py via package import machinery | package_initializer | yes |
| `core/cold_start.py` | tools/d261_live_fdt_arm_once.py | runtime_module | yes |
| `core/fdt_lifecycle.py` | core/persistent_runtime.py | runtime_module | yes |
| `core/fdt_seed.py` | tools/d261_live_fdt_arm_once.py | runtime_module | yes |
| `core/persistent_runtime.py` | tools/d261_live_fdt_arm_once.py | runtime_module | yes |
| `core/post_d4.py` | core/cold_start.py and core/fdt_lifecycle.py | runtime_module | yes |
| `core/protected_runtime.py` | tools/d261_live_fdt_arm_once.py | runtime_module | yes |
| `core/runtime_transport.py` | core/cold_start.py and tools/d261_live_fdt_arm_once.py | runtime_module | yes |
| `core/tls_b0.py` | core/fdt_lifecycle.py and core/persistent_runtime.py | runtime_module | yes |
| `core/usb_runtime.py` | tools/d261_live_fdt_arm_once.py | runtime_module | yes |
| `poc/goodix5125/tools/binding_reference/__init__.py` | core/protected_runtime.py via package import machinery | package_initializer | yes |
| `poc/goodix5125/tools/binding_reference/crypto_reference.py` | poc/goodix5125/tools/binding_reference/runtime.py | runtime_module | yes |
| `poc/goodix5125/tools/binding_reference/pe_parser.py` | poc/goodix5125/tools/binding_reference/runtime.py | runtime_module | yes |
| `poc/goodix5125/tools/binding_reference/runtime.py` | poc/goodix5125/tools/binding_reference/__init__.py | runtime_module | yes |
| `src/goodix5125_cleanroom.py` | core/post_d4.py and core/fdt_seed.py | runtime_module | yes |
| `tools/d261_live_fdt_arm_once.py` | operator_kit/d261-live-fdt-arm-once.sh | python_entrypoint | yes |

All listed files execute repository-local Python code on the supported import path; namespace-package directories without `__init__.py` are intentionally absent.
