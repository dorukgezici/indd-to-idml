# Contributing

Bug reports and focused pull requests are welcome. Read the conversion limits in the README before proposing changes to fidelity claims.

## Development

```sh
npm ci
uv sync --locked
npm test
node --check src/indd_to_idml/photopea.mjs
```

The tests generate their own synthetic inputs and run without Photopea, Affinity, or private documents. An end-to-end INDD conversion requires an internet connection, Chromium, and a document you have permission to use.

## Reporting a conversion issue

Include your operating system, CLI version, INDD version, command, relevant error, and a description of expected versus actual behavior. For layout problems, include the affected feature, such as a text frame, crop, or mask. If you can share a minimal reproducer, remove private information and ensure you have permission to redistribute it.

Reports can contain filenames, absolute paths, font names, source hashes, and linked-image metadata. Redact them before posting. Do not attach commercial fonts or client documents without permission.

## Code changes

Add a regression test for changed parsing, geometry, text, or failure handling. Keep the layered importer and the IDML writer separate. Preserve Unicode text and coordinate transforms, and report unsupported features honestly. Never silently replace corrupt image channels or flatten a page to claim successful editable conversion.

Changes involving the browser engine need a fresh, uncached INDD conversion. Changes to IDML geometry or typography need a visual check in Affinity or InDesign. State which checks you completed in the pull request. Private sample audits are not part of public CI.

Contributions are licensed under the repository's MIT license. Include attribution and compatible license notices for any third-party code you add.
