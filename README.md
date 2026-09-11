# INDD to editable IDML

[![CI](https://github.com/dorukgezici/indd-to-idml/actions/workflows/ci.yml/badge.svg)](https://github.com/dorukgezici/indd-to-idml/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A command-line converter for opening InDesign documents in Affinity. It imports INDD through Photopea in a headless local browser, then reconstructs IDML with native text frames, vector paths, groups, and linked images.

**This is an editable reconstruction, not a lossless InDesign export.** Version 0.1.0 was verified on three private documents opened in Affinity 3.2.3. A heading was edited in Affinity to verify that text remains text. Adobe InDesign is not installed or required for this route.

## Run

```sh
git clone https://github.com/dorukgezici/indd-to-idml.git
cd indd-to-idml
npm ci
npm run setup:browser
mkdir -p in out
# Place your .indd files and their linked photos in in/ first.
./indd-to-idml
```

The defaults recursively read `in/` and write `out/`, preserving subdirectories. Setup requires [uv](https://docs.astral.sh/uv/), Node.js 22 or newer, and an internet connection to load Photopea. The launcher installs the pinned Python environment through `uv.lock`. On macOS, the installed Google Chrome is used automatically. Otherwise, install the browser once:

```sh
npm run setup:browser
```

You can also select a Chromium executable with `INDD_CHROME`.

```sh
# One file
./indd-to-idml 'in/My Document.indd' -o out

# Rebuild all outputs
./indd-to-idml in -o out --force

# Check ZIP/XML structure, object references, and local image links
./indd-to-idml --validate 'out/My Document.idml'

# Inspect source version and advisory metadata without loading Photopea
./indd-to-idml in --inspect

# Tests
npm test
```

The converter refuses to overwrite an existing IDML unless `--force` is supplied. A failed batch continues with its remaining files and returns exit status 1. The source files are never edited, and their SHA-256 digests are checked after conversion.

Each output consists of an `.idml`, an `_assets/` directory, and a `.report.json`. **Keep the assets.** Links currently contain absolute local file URIs; moving the output requires relinking images in Affinity or regenerating it at the new location. Photos are decoded to PNG at their original pixel dimensions, which can use substantially more space than JPEG or AVIF.

## Verification

| Document | Pages | Editable text frames | Placed images | Distinct original photos restored |
| --- | ---: | ---: | ---: | ---: |
| Sample A | 20 | 54 | 20 | 8 |
| Sample B | 20 | 55 | 16 | 6 |
| Sample C | 37 | 109 | 31 | 14 |
| Total | 77 | 218 | 67 | 28 |

No objects in these samples needed rasterization during IDML reconstruction. Every text string in the imported layered documents is preserved in its corresponding IDML story. The source INDD files remained unchanged. These checks establish preservation of the intermediate import, not pixel identity with an Adobe rendering.

All three IDML files were opened in the installed Affinity 3.2.3. Page counts were confirmed as 20, 20, and 37. First-page headings and photos rendered; a heading was replaced with `EDITABLE TEXT`, then the modified document was closed without saving. This was a representative UI check, not a visual review of every object on every page.

Install the original fonts before opening the output. The converter preserves recovered font names and reports missing fonts; it does not redistribute or automatically install them. Different font versions can change wrapping. The verification documents still had two unavailable commercial fonts, so typography requiring those fonts was not verified.

Private documents and their reports are not included in the repository. Public CI runs synthetic tests on Linux and macOS. Full INDD import and Affinity checks are performed locally because they need a real document and the external applications.

To audit local documents in `in/` against their cached intermediates after conversion:

```sh
uv run python scripts/audit_samples.py
```

## What is preserved and what is limited

The writer retains page dimensions, object order, editable text and recovered formatting runs, groups, solid-fill Bezier geometry, affine image transforms, vector clipping paths, opacity, and supported blend modes. It handles Turkish filenames and text, including UTF-16 style offsets for characters outside the basic multilingual plane.

Photopea's importer may lose information before this writer sees it. InDesign story threading, named style definitions, master-page relationships, and print metadata are not retained. Tables, anchored objects, interactive features, complex typography, and advanced color management are not verified. This is not a prepress conversion tool. Photos become RGB/RGBA PNGs; CMYK and spot-color identity are not preserved.

Some unsupported individual objects can use their embedded raster preview, with each fallback listed in the report. Masked groups, clipping layers, unsupported blends, and layer effects fail explicitly when the writer cannot reconstruct them safely. Corrupt PSD image channels fail instead of silently becoming black pixels. A package passing `--validate` has passed this project's structural checks, not Adobe's full schema or a visual fidelity test.

The original linked-image paths in INDD often refer to unavailable volumes. The importer supplies embedded images. The converter searches each INDD's containing directory for supplied photos and restores a full-resolution candidate only when a color/spatial thumbnail comparison has a sufficiently strong, unambiguous match. Each chosen file and its match score are recorded. This is a heuristic, so inspect image matches in the report for unfamiliar documents.

When preservation of InDesign-specific features or exact Adobe composition is required, use InDesign's native IDML export. The researched open-source scripts for that route require a licensed InDesign installation. See [research findings](research/README.md).

## Engine and cache

The Python code and IDML writer run locally. The Node helper uses Photopea's documented Live Messaging API in an isolated headless Chromium process. INDD bytes are passed into the browser locally; PSD bytes return through a token-protected loopback HTTP endpoint. The helper blocks external non-GET/HEAD requests and WebSockets. It still needs the remote Photopea application and its fonts, so it is not an offline converter. Photopea is a third-party service and its importer can change independently of this project.

Successful layered intermediates are cached by source SHA-256 in `.cache/indd-to-idml/`. A fresh source import can take a minute or more and large PSD caches can consume gigabytes. The default timeout is 300 seconds per document; adjust with `--timeout`. Remove a source's cached PSD to reimport it after an engine update. Linked photos are rescanned on each reconstruction.

For diagnostics, `--intermediate FILE.psd` accepts an existing full Photopea PSD for a single input. The caller is responsible for pairing that PSD with the correct INDD. Minified Photopea PSDs are not supported because their channel compression caused decoding failures in testing. Normal conversion always requests a full PSD.

Use this project from its checkout. `npm ci` installs the Node helper's dependency alongside the Python package; installing just the Python wheel does not install Node or Playwright.

## Platform support

The complete conversion and Affinity workflow was tested on macOS. Linux runs the automated test suite and Chromium smoke test in CI; real INDD conversion on Linux has not been visually verified. Native Windows support is not verified. Python 3.11 or newer is required; uv can provision it automatically.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| Chromium executable missing | Run `npm run setup:browser` or set `INDD_CHROME`. On Linux, `npx playwright install --with-deps chromium` also installs required system libraries. |
| Engine timeout | Check network access to Photopea, then increase `--timeout`. |
| Missing fonts or different text wrapping | Install the document fonts in the target editor and reopen the IDML. |
| Missing image links after moving output | Relink the `_assets` folder in Affinity or regenerate at the new location. |
| Unsupported feature error | Use native InDesign export for that document; include a shareable minimal case in an issue. |

## License and contributions

The CLI is released under the [MIT license](LICENSE). Photopea is a proprietary hosted dependency, not part of this open-source release. See [third-party notices](THIRD_PARTY_NOTICES.md), [contribution guidelines](CONTRIBUTING.md), and the [changelog](CHANGELOG.md).
