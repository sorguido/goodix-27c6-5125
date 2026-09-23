# Documentation classification after public cleanup

The active public allowlist is `PUBLICATION_MANIFEST.md`; there is no whole-directory
export of docs, production, deployment or libfprint-driver. This internal record is
excluded from publication. Existing internal files remain in place, preserving links
and historical reconstruction; no public operation or R6 packaging is performed.

| Document | Classification | Treatment |
| --- | --- | --- |
| README.md, TECHNICAL_MANUAL.md, ACKNOWLEDGEMENTS.md | PUBLIC_STABLE_DOCUMENTATION | Current architecture/product rewrite |
| docs/INSTALLATION.md, UNINSTALL.md, DEVICE_MATERIALS.md, SECURITY.md, VALIDATION.md | PUBLIC_STABLE_DOCUMENTATION | Stable vocabulary; truthful package availability |
| docs/LICENSING_AND_PROVENANCE.md, REFERENCES.md, production/README.md | PUBLIC_TECHNICAL_REFERENCE | Current components, source audit and dependencies |
| docs/R4_PLASMA_LOGIN_INTEGRATION.md | INTERNAL_DEVELOPMENT_EVIDENCE | Excluded; stable architecture consolidated into public manual |
| docs/R5_INSTALL.md | INTERNAL_DEVELOPMENT_EVIDENCE | Excluded; no public installer invented |
| docs/STOCK_FPRINTD_ATTEMPTS.md | INTERNAL_DEVELOPMENT_EVIDENCE | Excluded; useful action semantics summarized in public manual |
| docs/MINIMAL_RUNTIME.md | INTERNAL_DEVELOPMENT_EVIDENCE | Excluded; current component inventory summarized in public manual |
| docs/DEVICE_MATERIAL_PIN_AUDIT.md | INTERNAL_DEVELOPMENT_EVIDENCE | Excluded; useful contracts consolidated into DEVICE_MATERIALS.md |
| deployment/recovery/*.md, deployment/minimal-runtime/*.md, deployment/plasma-login-opt-in/*.md | INTERNAL_DEVELOPMENT_EVIDENCE | All excluded from public docs |
| production/minimal-runtime/*.md | INTERNAL_DEVELOPMENT_EVIDENCE | Excluded; no VM/private-path public instructions |
| production/login/*.md, production/sudo/*.md, production/polkit/*.md, deployment/managed-install/*.md | HISTORICAL_ONLY | Excluded with those source components |
| libfprint-driver/README.md | INTERNAL_DEVELOPMENT_EVIDENCE | Excluded; no wildcard code-directory documentation export |
| GoodixArtifacts/opencv-4.13-rpms/README.md, reference/libfprint-fedora44-1.94.100/PROVENANCE.md | PUBLIC_TECHNICAL_REFERENCE | Reviewed stable build/source facts |
| Three explicitly listed upstream libfprint Markdown files | PUBLIC_TECHNICAL_REFERENCE | Original upstream text, notices and links retained |

The complete previous licensing ledger and device-material acquisition reference
are copied byte-for-byte under `before-public-cleanup/`. Their internal historical
information remains available without being presented as current public behavior.
Other previous documents remain reconstructible in Git. No protected file content
was read or copied for this documentation work.
