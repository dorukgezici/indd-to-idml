"""Read the documented INDD header and recover advisory XMP metadata.

XMP/string scans may contain obsolete save generations. They are not used to
infer the current page tree or current text content.
"""
from __future__ import annotations

import hashlib
import html
import re
import struct
from pathlib import Path
from urllib.parse import unquote

MAGIC = bytes.fromhex("0606edf5d81d46e5bd31efe7fe74b71d")


def inspect_indd(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 4096 or data[:16] != MAGIC or data[16:24] != b"DOCUMENT":
        raise ValueError(f"Not a supported INDD document: {path.name}")
    byte_order = {1: "<", 2: ">"}.get(data[24])
    if byte_order is None:
        raise ValueError("Invalid INDD byte order")
    major, minor = struct.unpack_from(byte_order + "II", data, 29)
    fonts = {}
    text = data.decode("utf-8", errors="replace")
    for item in re.findall(r"<rdf:li\b[^>]*>(.*?)</rdf:li>", text, re.S):
        fields = dict(re.findall(r"<stFnt:(\w+)>(.*?)</stFnt:\1>", item, re.S))
        if "fontName" in fields:
            fonts[html.unescape(fields["fontName"])] = {
                key: html.unescape(value) for key, value in fields.items()
            }
    urls = sorted({html.unescape(unquote(u)) for u in re.findall(
        r"file:/[^\s<>\x00\"\x01-\x1f]+\.(?:avif|jpe?g|png|tiff?|psd|pdf|eps|ai)",
        text, re.I,
    )})
    return {
        "name": path.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "version": {"major": major, "minor": minor}, "fonts": fonts,
        "historical_link_candidates": urls,
    }
