# Third-party software

The MIT license covers this repository's implementation. Dependencies retain their own licenses.

| Component | Purpose | License / source |
| --- | --- | --- |
| psd-tools | Layered PSD parsing | MIT, https://github.com/psd-tools/psd-tools |
| Pillow | Image decoding and PNG output | HPND, https://github.com/python-pillow/Pillow |
| NumPy | Image comparison and masks | BSD-3-Clause, https://github.com/numpy/numpy |
| lxml | IDML XML writing and validation | BSD-3-Clause, https://github.com/lxml/lxml |
| fontTools | Installed font inspection | MIT, https://github.com/fonttools/fonttools |
| Playwright | Local Chromium control | Apache-2.0, https://github.com/microsoft/playwright |
| pytest | Tests | MIT, https://github.com/pytest-dev/pytest |
| uv | Environment and dependency management | MIT OR Apache-2.0, https://github.com/astral-sh/uv |

Photopea is a proprietary, externally hosted application accessed through its documented [API](https://www.photopea.com/api/). Its source code and license are not included in this repository. Chromium is installed separately by Playwright or supplied by the user and has its own third-party notices.

Adobe, InDesign, Affinity, and Photopea are names of their respective products and owners. This project is independent and is not affiliated with or endorsed by them.

No input documents, photos, converted documents, or font files are distributed with this release. The open-source projects consulted during implementation are linked in [research/README.md](research/README.md).
