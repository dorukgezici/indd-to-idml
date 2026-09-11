# Changelog

## 0.1.0 - 2026-09-11

Initial public release of the INDD-to-IDML reconstruction CLI.

- Recursive conversion with preserved output subdirectories and per-document reports.
- Local headless Photopea import, SHA-256 intermediate caching, and source integrity checks.
- Native IDML text frames, Unicode formatting runs, groups, solid vector paths, and image frames.
- Image transform and clipping recovery, with matching supplied original photos.
- Font availability reporting and explicit unsupported-feature errors.
- ZIP/XML, object-reference, and linked-image validation.
- Automated synthetic tests and documented Affinity verification on three private documents.

This release is intended for editable migration. It does not preserve all InDesign features or establish pixel-identical output. See the README for limits and the hosted-engine dependency.
