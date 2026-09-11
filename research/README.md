# Conversion research

Research and local verification performed on 11 September 2026.

## Native export projects

[dl6nm/adobe-indesign-script-collection](https://github.com/dl6nm/adobe-indesign-script-collection/blob/main/convert-INDD-to-IDML.jsx) provides a short ExtendScript workflow: open each INDD, update links, export `ExportFormat.INDESIGN_MARKUP`, and close without saving. It runs inside InDesign. This is useful as a native-export reference, but it does not decode INDD independently.

[konradvb/indd-to-idml-converter](https://github.com/konradvb/indd-to-idml-converter) automates InDesign 2026 with AppleScript on macOS. Its dependency on InDesign remains, and missing fonts and links affect conversion.

[Starou/SimpleIDML](https://github.com/Starou/SimpleIDML) is an established Python project for manipulating IDML packages. Its native INDD workflows use InDesign Server. Adobe-generated IDML samples in that project's regression tests helped establish the package and XML layout used here. No source converter code was copied into the implementation.

[paged-media/awesome-idml](https://github.com/paged-media/awesome-idml) helped identify related tools. [yzyly1992/PDF2IDML](https://github.com/yzyly1992/PDF2IDML) concerns an experimental PDF route, which cannot recover the original INDD document model. Research did not identify a usable open-source independent INDD layout parser for these samples. This is a research finding, not a claim that none can exist.

## Independent import route

Photopea documents [INDD support](https://blog.photopea.com/photopea-5-3-support-for-indesign-and-krita-files.html), including layered text, images, and vector content, and [opening INDD without InDesign](https://www.photopea.com/tuts/open-indd-files-without-indesign/). Its [Live Messaging API](https://www.photopea.com/api/live) accepts binary ArrayBuffers and returns exported document bytes. [Scripting documentation](https://www.photopea.com/learn/scripts) describes its Photoshop-compatible document API.

The application uses that documented interface to obtain a layered PSD, then writes IDML itself. It does not use a PDF or flatten whole pages. Photopea's INDD importer is proprietary and externally hosted; this project is not a standalone open-source INDD parser.

[psd-tools](https://github.com/psd-tools/psd-tools) exposes PSD artboards, text engine data, smart-object images and transforms, and vector masks. It proved usable for all three supplied documents. [ag-psd](https://github.com/Agamnentzar/ag-psd) was investigated first, but the very tall intermediate documents and mask handling were obstacles for that route.

## Format and interoperability findings

* The binary INDD header contains a signature, byte order, and version. Font/link strings and XMP can remain from older saves. They cannot reliably determine the current page tree or text. This converter uses metadata scans only for advisory links and font names.
* IDML is a ZIP package. Its uncompressed first entry identifies the IDML MIME type. The document manifest links resources, spreads, and stories; unique object IDs link frames and content.
* PSD text run lengths use UTF-16 code units. Slicing Python strings with those offsets corrupts formatting after emoji and other supplementary characters. The writer translates offsets explicitly.
* The importer stores pages as artboards arranged on a tall canvas. Every object's coordinates must be translated back into its page's coordinate space.
* Embedded images can be low-resolution previews even when the layout is otherwise editable. Supplied linked photos must be recovered separately while retaining the crop and transform.
* A PSD vector mask can also have a generated pixel mask. Applying both can cause unnecessary rasterization or edge degradation. The writer recognizes the generated-mask flag and retains the native vector clip.
* Minified Photopea PSD export triggered ZIP prediction/checksum decoding failures with the tested psd-tools version. Full PSD export succeeded. Decompression warnings are treated as errors.
* Missing fonts change wrapping and layout in Affinity even when text, sizes, and frame geometry are preserved. The Montserrat fonts came from the [official repository](https://github.com/JulietaUla/Montserrat) with its OFL license. Commercial Azo Sans and Proxima Nova were unavailable.
* Affinity supports [IDML import](https://support.serif.com/hc/en-us/articles/10259217288463-Is-it-possible-to-import-INDD-or-IDML-Adobe-InDesign-files-into-Affinity). Importing any interchange format can require adjustments. The final outputs were tested in the locally installed Affinity, in addition to ZIP/XML checks.

## Validation boundary

The sample audit compares all reconstructed text and page counts against the Photopea intermediate, verifies unchanged INDD hashes, and resolves every generated image link. Manual Affinity checks confirmed all three documents open and demonstrated a native text edit. Neither an Adobe InDesign render nor a full visual comparison of all pages was available. Consequently these results support an editable migration workflow, not a universal lossless-conversion claim.
