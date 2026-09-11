"""Convert a Photopea layered intermediate to native IDML objects.

This is reconstruction, not Adobe's lossless native export. Every fallback is
recorded in the accompanying report. The INDD is never edited.
"""
from __future__ import annotations

import hashlib
import io
import re
import warnings
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from psd_tools import PSDImage
from psd_tools.constants import Tag
from psd_tools.compression import PSDDecompressionWarning

from .idml import Package, node, num, nums, properties, path_geometry


def plain(value):
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(getattr(k, "value", k)): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)) or type(value).__name__ == "List":
        return [plain(v) for v in value]
    return getattr(value, "value", value)


def fingerprint(im):
    return np.asarray(im.convert("RGB").resize((48, 48), Image.Resampling.LANCZOS), dtype=np.float32) / 255


class Assets:
    def __init__(self, source_dir, output_dir, report):
        self.output_dir = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        self.report = report
        self.saved = {}
        self.candidates = []
        for file in sorted(source_dir.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in {".jpg", ".jpeg", ".png", ".avif", ".webp", ".tif", ".tiff"}:
                continue
            try:
                with Image.open(file) as opened:
                    im = ImageOps.exif_transpose(opened)
                    self.candidates.append((file, im.size, fingerprint(im)))
            except (OSError, ValueError):
                pass

    def save(self, raw, name="image", restore=True):
        digest = hashlib.sha256(raw).hexdigest()
        if digest in self.saved:
            return self.saved[digest]
        im = Image.open(io.BytesIO(raw))
        im.load()
        origin = None
        metric = None
        if restore:
            fp = fingerprint(im)
            scores = []
            for file, size, candidate in self.candidates:
                if abs(size[0] / size[1] / (im.width / im.height) - 1) > 0.02:
                    continue
                error = float(np.sqrt(np.mean((fp - candidate) ** 2)))
                scores.append((error, file))
            scores.sort()
            # Color and spatial match, plus a clear winner. Never guess from a name.
            if scores and scores[0][0] < 0.045 and (len(scores) == 1 or scores[1][0] - scores[0][0] > 0.015):
                metric, origin = scores[0]
                with Image.open(origin) as opened:
                    im = ImageOps.exif_transpose(opened).copy()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "transparency" in im.info else "RGB")
        filename = re.sub(r"[^\w.-]+", "-", origin.stem if origin else name).strip("-.")[:70] or "image"
        dest = self.output_dir / f"{filename}-{digest[:12]}.png"
        # IDML GraphicBounds uses pixels at 72 ppi; normalize the physical resolution.
        im.save(dest, dpi=(72, 72))
        entry = {"file": dest.name, "pixels": list(im.size), "restored_from": str(origin) if origin else None, "match_rmse": metric, "source": "supplied_original" if origin else "embedded_intermediate"}
        self.report["assets"].append(entry)
        self.saved[digest] = (dest, im.size)
        return dest, im.size


def font_info(name, metadata):
    f = metadata.get("fonts", {}).get(name, {})
    if f.get("fontFamily"):
        return {"postscript": name, "family": f["fontFamily"], "style": f.get("fontFace", "Regular")}
    parts = name.rsplit("-", 1)
    family = parts[0]
    family = {"ProximaNova": "Proxima Nova", "AzoSans": "Azo Sans", "MyriadPro": "Myriad Pro", "MyriadHebrew": "Myriad Hebrew", "ArialMT": "Arial"}.get(family, family)
    style = parts[1] if len(parts) == 2 else "Regular"
    style = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", style).replace("Semi Bold", "SemiBold")
    return {"postscript": name, "family": family, "style": style}


def color_value(style):
    color = style.get("FillColor", {"Type": 1, "Values": [1, 0, 0, 0]})
    vals = color.get("Values", [1, 0, 0, 0])
    if color.get("Type") == 2 and len(vals) >= 5:
        _, c, m, y, k = vals[:5]
        return [255 * (1 - c) * (1 - k), 255 * (1 - m) * (1 - k), 255 * (1 - y) * (1 - k)]
    if len(vals) >= 4:
        return [255 * x for x in vals[1:4]]
    return [0, 0, 0]


def utf16_offsets(text):
    """Translate PSD run offsets (UTF-16 code units) into Python indices."""
    offsets = {0: 0}
    units = 0
    for index, char in enumerate(text, 1):
        units += 2 if ord(char) > 0xffff else 1
        offsets[units] = index
    # Photoshop appends one paragraph sentinel to its run arrays.
    offsets[units + 1] = len(text)
    return offsets


def text_paragraphs(layer, metadata):
    engine = plain(layer.engine_dict)
    resource = plain(layer.resource_dict)
    # The PSD Editor adds a sentinel paragraph; layer.text excludes that sentinel.
    text = layer.text.replace("\x00", "")
    offsets = utf16_offsets(text)
    styles = engine["StyleRun"]
    paras = engine["ParagraphRun"]
    default = resource["StyleSheetSet"][0]["StyleSheetData"]
    runs = []
    offset = 0
    for length, run in zip(styles["RunLengthArray"], styles["RunArray"]):
        runs.append((offsets[offset], offsets[offset + length], {**default, **run["StyleSheet"]["StyleSheetData"]}))
        offset += length
    pruns = []
    offset = 0
    for length, run in zip(paras["RunLengthArray"], paras["RunArray"]):
        pruns.append((offsets[offset], offsets[offset + length], run["ParagraphSheet"]["Properties"]))
        offset += length
    result = []
    position = 0
    # Split at actual paragraph boundaries as well as formatting runs.
    for segment in text.splitlines(keepends=True) or [text]:
        end = position + len(segment)
        pstyle = next((s for a, b, s in pruns if a <= position < b), {})
        just = ["LeftAlign", "RightAlign", "CenterAlign", "LeftJustified", "RightJustified", "CenterJustified", "FullyJustified"]
        attrs = {"Justification": just[int(pstyle.get("Justification", 0)) % len(just)], "Hyphenation": bool(pstyle.get("AutoHyphenate", False)), "AutoLeading": num(pstyle.get("AutoLeading", 1.2) * 100)}
        for a, b in [("FirstLineIndent", "FirstLineIndent"), ("StartIndent", "LeftIndent"), ("EndIndent", "RightIndent"), ("SpaceBefore", "SpaceBefore"), ("SpaceAfter", "SpaceAfter")]:
            attrs[b] = num(pstyle.get(a, 0))
        p = {"attrs": attrs, "runs": []}
        for start, stop, style in runs:
            a, b = max(start, position), min(stop, end)
            if a >= b:
                continue
            content = text[a:b]
            font = font_info(resource["FontSet"][int(style["Font"])]["Name"], metadata)
            char_attrs = {"FontStyle": font["style"], "PointSize": num(style.get("FontSize", 12)), "Tracking": num(style.get("Tracking", 0)), "HorizontalScale": num(style.get("HorizontalScale", 1) * 100), "VerticalScale": num(style.get("VerticalScale", 1) * 100), "BaselineShift": num(style.get("BaselineShift", 0)), "Underline": bool(style.get("Underline", False)), "StrikeThru": bool(style.get("Strikethrough", False)), "Ligatures": bool(style.get("Ligatures", True)), "Capitalization": {0: "Normal", 1: "SmallCaps", 2: "AllCaps"}.get(style.get("FontCaps", 0), "Normal")}
            r = {"text": content.rstrip("\r\n"), "break": content.endswith(("\r", "\n")), "attrs": char_attrs, "font": font, "color": color_value(style)}
            if not style.get("AutoLeading", True) and style.get("Leading", 0) > 0:
                r["leading"] = style["Leading"]
            p["runs"].append(r)
        result.append(p)
        position = end
    return result, engine


BLENDS = {b"norm": "Normal", b"pass": "Normal", b"mul ": "Multiply", b"scrn": "Screen", b"over": "Overlay", b"dark": "Darken", b"lite": "Lighten", b"diff": "Difference", b"smud": "Exclusion", b"hue ": "Hue", b"sat ": "Saturation", b"colr": "Color", b"lum ": "Luminosity"}


def rgb_descriptor(desc):
    if desc is None or b"Clr " not in desc:
        return None
    c = desc[b"Clr "]
    if all(k in c for k in (b"Rd  ", b"Grn ", b"Bl  ")):
        return [float(c[k]) for k in (b"Rd  ", b"Grn ", b"Bl  ")]
    return None


def convert_psd(intermediate: Path, source: Path, destination: Path, metadata: dict):
    with warnings.catch_warnings():
        # psd-tools otherwise replaces corrupt channels with black pixels.
        warnings.simplefilter("error", PSDDecompressionWarning)
        return _convert_psd(intermediate, source, destination, metadata)


def _convert_psd(intermediate: Path, source: Path, destination: Path, metadata: dict):
    psd = PSDImage.open(intermediate, max_alloc_bytes=1024**3)
    report = {"source": metadata, "engine": "photopea-reconstruction", "native_adobe_export": False,
              "fidelity": "reconstructed", "warnings": [], "assets": [], "pages": [], "fonts": [], "rasterized_objects": [],
              "limitations": ["InDesign story threading, named styles, master-page relationships and print metadata are not retained by the intermediate importer.", "Fonts must be available in Affinity. A structurally valid IDML does not establish visual identity with InDesign.", "Photopea may omit or approximate unsupported INDD features before IDML reconstruction."]}
    package = Package()
    assets = Assets(source.parent, destination.parent / (destination.stem.removesuffix(".partial") + "_assets"), report)
    artboards = list(psd)
    if not artboards or any(a.kind != "artboard" for a in artboards):
        raise ValueError("INDD importer did not produce an explicit page/artboard tree")
    if len(artboards) > 1000:
        raise ValueError("Document exceeds 1000-page limit")

    def rasterize(layer, parent, ox, oy, page, reason):
        # Preserve the object's appearance, not an entire page, when native export
        # of that object's geometry is unavailable.
        image = layer.topil()
        if image is None:
            raise ValueError(f"Cannot export {layer.kind} object {layer.name!r}: {reason}")
        if layer.has_mask() and not layer.mask.disabled:
            mask = layer.mask.topil()
            if mask is not None:
                canvas = Image.new("L", image.size, layer.mask.background_color)
                canvas.paste(mask, (layer.mask.left - layer.left, layer.mask.top - layer.top))
                if image.mode != "RGBA": image = image.convert("RGBA")
                alpha = np.asarray(image.getchannel("A"), dtype=np.uint16) * np.asarray(canvas, dtype=np.uint16) // 255
                image.putalpha(Image.fromarray(alpha.astype(np.uint8)))
        buf = io.BytesIO(); image.save(buf, format="PNG")
        file, size = assets.save(buf.getvalue(), layer.name, restore=False)
        x, y = layer.left - ox, layer.top - oy
        item = package.add_image(parent, layer.name, file, size, (1, 0, 0, 1, x, y), (x, y, x + size[0], y + size[1]), layer.opacity / 255)
        item.set("Visible", str(layer.visible).lower())
        report["rasterized_objects"].append({"page": page, "name": layer.name, "kind": layer.kind, "reason": reason})

    def visit(layer, parent, ox, oy, page):
        blend = BLENDS.get(layer.blend_mode.value)
        if blend is None or layer.has_effects():
            raise ValueError(f"Unsupported blending or layer effects require native export: {layer.name}")
        opacity = layer.opacity / 255
        if layer.is_group():
            if layer.has_mask() or layer.has_vector_mask():
                raise ValueError(f"Masked group requires a native conversion engine: {layer.name}")
            group = package.item(parent, "Group", layer.name)
            group.set("Visible", str(layer.visible).lower())
            package.transparency(group, opacity, blend)
            for child in layer:
                visit(child, group, ox, oy, page)
            return
        if layer.clipping:
            raise ValueError(f"Clipping layer requires a native conversion engine: {layer.name}")
        if layer.kind == "type":
            paragraphs, engine = text_paragraphs(layer, metadata)
            transform = list(layer.transform)
            transform[4] -= ox; transform[5] -= oy
            shapes = engine.get("Rendered", {}).get("Shapes", {}).get("Children", [])
            box = shapes[0].get("Cookie", {}).get("Photoshop", {}).get("BoxBounds") if shapes else None
            if box is None:
                # Point text: derive a local box from the type descriptor bounds.
                b = layer._data.text_data.get(b"bounds")
                if b is None: raise ValueError("Point text has no recoverable bounds")
                box = [float(b[k]) for k in (b"Left", b"Top ", b"Rght", b"Btom")]
                report["warnings"].append(f"Page {page}: point text converted to a text frame: {layer.name}")
            item = package.add_text(parent, layer.name.rstrip("\r\n"), transform, box, paragraphs, opacity, blend)
            item.find("TextFramePreference").set("FirstBaselineOffset", "CapHeight")
        elif layer.kind == "shape":
            fill = rgb_descriptor(layer.tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING))
            stroke = None; width = 0
            if layer.stroke:
                if not layer.stroke.fill_enabled: fill = None
                if layer.stroke.enabled:
                    stroke = rgb_descriptor(layer.stroke.content)
                    width = layer.stroke.line_width
            if layer.vector_mask is None or layer.vector_mask.inverted or (fill is None and stroke is None):
                rasterize(layer, parent, ox, oy, page, "non-solid fill or unsupported vector mask")
                return
            paths = []
            for sub in layer.vector_mask.paths:
                def point(p): return (p[1] * psd.width - ox, p[0] * psd.height - oy)
                paths.append((sub.is_closed(), [(point(k.anchor), point(k.preceding), point(k.leaving)) for k in sub]))
            item = package.add_shape(parent, layer.name, paths, fill, stroke, width, opacity, blend)
        elif layer.kind == "smartobject":
            obj = layer.smart_object
            raw = obj.data
            try:
                original = Image.open(io.BytesIO(raw))
                original.verify()
            except (OSError, ValueError):
                rasterize(layer, parent, ox, oy, page, "non-raster smart object")
                return
            file, size = assets.save(raw)
            q = obj.transform_box
            if q is None: raise ValueError("Image has no transform")
            x0, y0, x1, y1, x2, y2, x3, y3 = q
            if abs(x0 + x2 - x1 - x3) > .02 or abs(y0 + y2 - y1 - y3) > .02:
                rasterize(layer, parent, ox, oy, page, "perspective image transform")
                return
            transform = [(x1-x0)/size[0], (y1-y0)/size[0], (x3-x0)/size[1], (y3-y0)/size[1], x0-ox, y0-oy]
            clip = (layer.left-ox, layer.top-oy, layer.right-ox, layer.bottom-oy)
            if layer.has_mask() and not layer.mask.disabled and not (layer.has_vector_mask() and layer.mask._data.flags.user_mask_from_render):
                mask = layer.mask
                mask_image = mask.topil()
                if mask_image is not None and mask_image.getextrema()[0] < 254:
                    rasterize(layer, parent, ox, oy, page, "nonrectangular image mask")
                    return
                clip = (mask.left-ox, mask.top-oy, mask.right-ox, mask.bottom-oy)
            item = package.add_image(parent, layer.name, file, size, transform, clip, opacity, blend)
            if layer.has_vector_mask():
                if layer.vector_mask.inverted:
                    raise ValueError("Inverted image vector mask is unsupported")
                paths = []
                for sub in layer.vector_mask.paths:
                    def point(p): return (p[1] * psd.width - ox, p[0] * psd.height - oy)
                    paths.append((sub.is_closed(), [(point(k.anchor), point(k.preceding), point(k.leaving)) for k in sub]))
                prop = properties(item)
                prop.remove(prop.find("PathGeometry"))
                path_geometry(item, paths)
        else:
            rasterize(layer, parent, ox, oy, page, "pixel or unsupported object")
            return
        item.set("Visible", str(layer.visible).lower())

    for index, artboard in enumerate(artboards, 1):
        x0, y0, x1, y1 = artboard.bbox
        width, height = x1-x0, y1-y0
        spread = package.add_page(width, height, index)
        for layer in artboard:
            visit(layer, spread, x0, y0, index)
        report["pages"].append({"page": index, "width_pt": width, "height_pt": height, "source_artboard": artboard.name, "text_objects": sum(l.kind == "type" for l in artboard.descendants())})
    report["validation"] = package.finish(destination)
    report["fonts"] = sorted(package.fonts.values(), key=lambda f: f["postscript"])
    recovered = sum(a["source"] == "supplied_original" for a in report["assets"])
    report["restored_original_images"] = recovered
    report["embedded_image_assets"] = len(report["assets"]) - recovered
    if report["embedded_image_assets"]:
        report["warnings"].append(f"{report['embedded_image_assets']} image assets use embedded data; original resolution may be unavailable.")
    return report
