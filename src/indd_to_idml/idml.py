"""Small IDML writer, with native text, Bezier paths and linked images."""
from __future__ import annotations

import math
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse
from lxml import etree as E

NS = "http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
MIME = b"application/vnd.adobe.indesign-idml-package"


def num(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Non-finite geometry")
    return f"{value:.8f}".rstrip("0").rstrip(".") or "0"


def nums(values):
    return " ".join(num(v) for v in values)


def node(parent, tag, **attrs):
    return E.SubElement(parent, tag, {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in attrs.items()})


def properties(parent):
    found = parent.find("Properties")
    return found if found is not None else node(parent, "Properties")


def rect_path(parent, bounds):
    x0, y0, x1, y1 = bounds
    points = [(x0, y0), (x0, y1), (x1, y1), (x1, y0)]
    path_geometry(parent, [(True, [(p, p, p) for p in points])])


def path_geometry(parent, paths):
    geom = node(properties(parent), "PathGeometry")
    for closed, knots in paths:
        arr = node(node(geom, "GeometryPathType", PathOpen=not closed), "PathPointArray")
        for anchor, before, after in knots:
            node(arr, "PathPointType", Anchor=nums(anchor), LeftDirection=nums(before), RightDirection=nums(after))


class Package:
    def __init__(self):
        self.entries = {}
        self.counter = 0
        self.stories = []
        self.colors = {}
        self.fonts = {}
        self.document = E.Element("Document", nsmap={"idPkg": NS}, DOMVersion="8.0", Self="d", ZeroPoint="0 0", ActiveLayer="layer1")
        for tag, file in [("Graphic", "Graphic"), ("Fonts", "Fonts"), ("Styles", "Styles"), ("Preferences", "Preferences")]:
            node(self.document, f"{{{NS}}}{tag}", src=f"Resources/{file}.xml")
        layer = node(self.document, "Layer", Self="layer1", Name="Artwork", Visible=True, Locked=False, Printable=True, IgnoreWrap=False)
        node(properties(layer), "LayerColor", type="enumeration").text = "LightBlue"
        self.pages = []

    def uid(self):
        self.counter += 1
        return f"u{self.counter:x}"

    def root(self, tag):
        return E.Element(f"{{{NS}}}{tag}", nsmap={"idPkg": NS}, DOMVersion="8.0")

    def color(self, rgb):
        key = tuple(round(max(0, min(255, float(v))), 5) for v in rgb)
        if key not in self.colors:
            self.colors[key] = "Color/" + self.uid()
        return self.colors[key]

    def add_page(self, width, height, name):
        if width <= 0 or height <= 0:
            raise ValueError("Invalid page size")
        root = self.root("Spread")
        sid = self.uid()
        spread = node(root, "Spread", Self=sid, PageCount="1", BindingLocation="0", AllowPageShuffle=False, ItemTransform="1 0 0 1 0 0", ShowMasterItems=True)
        page = node(spread, "Page", Self=self.uid(), Name=str(name), AppliedMaster="n", GeometricBounds=nums((0, 0, height, width)), ItemTransform="1 0 0 1 0 0", MasterPageTransform="1 0 0 1 0 0", LayoutRule="Off")
        node(page, "MarginPreference", ColumnCount="1", ColumnGutter="0", Top="0", Bottom="0", Left="0", Right="0")
        filename = f"Spreads/Spread_{sid}.xml"
        self.entries[filename] = root
        node(self.document, f"{{{NS}}}Spread", src=filename)
        self.pages.append((width, height, page.get("Self")))
        return spread

    def item(self, parent, tag, name, transform=(1, 0, 0, 1, 0, 0), **attrs):
        element = node(parent, tag, Self=self.uid(), Name=name, ItemTransform=nums(transform), ItemLayer="layer1", Visible=True, Locked=False, AppliedObjectStyle="ObjectStyle/$ID/[None]", **attrs)
        return element

    def transparency(self, item, opacity=1.0, blend="Normal"):
        if opacity < 1 or blend != "Normal":
            node(node(item, "TransparencySetting"), "BlendingSetting", Opacity=num(opacity * 100), BlendMode=blend, KnockoutGroup=False, IsolateBlending=False)

    def add_image(self, parent, name, file: Path, image_size, transform, clip, opacity=1, blend="Normal"):
        frame = self.item(parent, "Rectangle", name, ContentType="GraphicType", FillColor="Swatch/None", StrokeColor="Swatch/None", StrokeWeight="0")
        rect_path(frame, clip)
        image = node(frame, "Image", Self=self.uid(), ItemTransform=nums(transform), ActualPpi="72 72", Space="$ID/#Links_RGB", ImageTypeName="$ID/PNG", Visible=True)
        node(properties(image), "GraphicBounds", Left="0", Top="0", Right=num(image_size[0]), Bottom=num(image_size[1]))
        node(image, "Link", Self=self.uid(), LinkResourceURI=file.resolve().as_uri(), LinkResourceFormat="$ID/PNG", StoredState="Normal", LinkClassID="35906", LinkClientID="257", LinkResourceModified=False, LinkObjectModified=False, ShowInUI=True, CanEmbed=True, CanUnembed=True, CanPackage=True, ImportPolicy="NoAutoImport", ExportPolicy="NoAutoExport")
        self.transparency(frame, opacity, blend)
        return frame

    def add_shape(self, parent, name, paths, color, stroke=None, stroke_width=0, opacity=1, blend="Normal"):
        shape = self.item(parent, "Polygon", name, ContentType="Unassigned", FillColor=self.color(color) if color is not None else "Swatch/None", StrokeColor=self.color(stroke) if stroke is not None else "Swatch/None", StrokeWeight=num(stroke_width))
        path_geometry(shape, paths)
        self.transparency(shape, opacity, blend)
        return shape

    def add_text(self, parent, name, transform, box, paragraphs, opacity=1, blend="Normal"):
        sid = self.uid()
        self.stories.append(sid)
        root = self.root("Story")
        story = node(root, "Story", Self=sid, AppliedTOCStyle="n", TrackChanges=False)
        node(story, "StoryPreference", OpticalMarginAlignment=False, FrameType="TextFrameType", StoryOrientation="Horizontal", StoryDirection="LeftToRightDirection")
        for para in paragraphs:
            p = node(story, "ParagraphStyleRange", AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle", **para["attrs"])
            for run in para["runs"]:
                attrs = dict(run["attrs"])
                font = run["font"]
                self.fonts[font["postscript"]] = font
                attrs["FillColor"] = self.color(run["color"])
                c = node(p, "CharacterStyleRange", AppliedCharacterStyle="CharacterStyle/$ID/[No character style]", **attrs)
                node(properties(c), "AppliedFont", type="string").text = font["family"]
                if "leading" in run:
                    node(properties(c), "Leading", type="unit").text = num(run["leading"])
                node(c, "Content").text = run["text"]
                if run.get("break"):
                    node(c, "Br")
        self.entries[f"Stories/Story_{sid}.xml"] = root
        frame = self.item(parent, "TextFrame", name, transform, ParentStory=sid, PreviousTextFrame="n", NextTextFrame="n", ContentType="TextType", FillColor="Swatch/None", StrokeColor="Swatch/None", StrokeWeight="0")
        rect_path(frame, box)
        prefs = node(frame, "TextFramePreference", TextColumnCount="1", TextColumnGutter="0", VerticalJustification="TopAlign", FirstBaselineOffset="FixedHeight", MinimumFirstBaselineOffset="0", IgnoreWrap=True, UseFixedColumnWidth=False)
        inset = node(properties(prefs), "InsetSpacing", type="list")
        for _ in range(4):
            node(inset, "ListItem", type="unit").text = "0"
        self.transparency(frame, opacity, blend)
        return frame

    def finish(self, destination: Path):
        if not self.pages:
            raise ValueError("No pages to export")
        self.document.set("StoryList", " ".join(self.stories))
        for sid in self.stories:
            node(self.document, f"{{{NS}}}Story", src=f"Stories/Story_{sid}.xml")
        node(self.document, "Section", Self=self.uid(), Name="", PageStart=self.pages[0][2], Length=str(len(self.pages)), ContinueNumbering=False, PageNumberStart="1", IncludeSectionPrefix=False, SectionPrefix="", Marker="", PageNumberStyle="Arabic")
        graphics = self.root("Graphic")
        node(graphics, "Swatch", Self="Swatch/None", Name="$ID/None", ColorEditable=False, ColorRemovable=False, Visible=True, SwatchType="None")
        for rgb, uid in self.colors.items():
            node(graphics, "Color", Self=uid, Name="RGB " + nums(rgb), Model="Process", Space="RGB", ColorValue=nums(rgb), ColorEditable=True, ColorRemovable=True, Visible=True)
        fonts = self.root("Fonts")
        families = {}
        for name, f in self.fonts.items():
            if f["family"] not in families:
                families[f["family"]] = node(fonts, "FontFamily", Self=self.uid(), Name=f["family"])
            node(families[f["family"]], "Font", Self=self.uid(), FontFamily=f["family"], Name=f["family"] + " " + f["style"], PostScriptName=name, FontStyleName=f["style"], FontType="OpenTypeTrueType")
        styles = self.root("Styles")
        node(node(styles, "RootCharacterStyleGroup", Self="rcsg"), "CharacterStyle", Self="CharacterStyle/$ID/[No character style]", Name="$ID/[No character style]")
        node(node(styles, "RootParagraphStyleGroup", Self="rpsg"), "ParagraphStyle", Self="ParagraphStyle/$ID/NormalParagraphStyle", Name="$ID/NormalParagraphStyle")
        node(node(styles, "RootObjectStyleGroup", Self="rosg"), "ObjectStyle", Self="ObjectStyle/$ID/[None]", Name="$ID/[None]")
        prefs = self.root("Preferences")
        node(prefs, "DocumentPreference", PageWidth=num(self.pages[0][0]), PageHeight=num(self.pages[0][1]), FacingPages=False, PagesPerDocument=str(len(self.pages)), DocumentBleedTopOffset="0", DocumentBleedBottomOffset="0", DocumentBleedInsideOrLeftOffset="0", DocumentBleedOutsideOrRightOffset="0")
        node(prefs, "ViewPreference", HorizontalMeasurementUnits="Points", VerticalMeasurementUnits="Points", RulerOrigin="PageOrigin")
        self.entries.update({"designmap.xml": self.document, "Resources/Graphic.xml": graphics, "Resources/Fonts.xml": fonts, "Resources/Styles.xml": styles, "Resources/Preferences.xml": prefs})
        container = E.Element("container", nsmap={None: "urn:oasis:names:tc:opendocument:xmlns:container"}, version="1.0")
        E.SubElement(E.SubElement(container, "rootfiles"), "rootfile", {"full-path": "designmap.xml", "media-type": "text/xml"})
        self.entries["META-INF/container.xml"] = container
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("mimetype", MIME, compress_type=zipfile.ZIP_STORED)
            for filename, root in self.entries.items():
                data = E.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True, pretty_print=True)
                if filename == "designmap.xml":
                    head, tail = data.split(b"\n", 1)
                    data = head + b'\n<?aid style="50" type="document" readerVersion="6.0" featureSet="257" product="8.0(370)" ?>\n' + tail
                z.writestr(filename, data)
        return validate(destination)


def validate(path: Path):
    parser = E.XMLParser(resolve_entities=False, no_network=True)
    with zipfile.ZipFile(path) as z:
        files = z.namelist()
        if len(files) > 10000 or sum(i.file_size for i in z.infolist()) > 256 * 1024**2:
            raise ValueError("IDML package exceeds validation limits")
        if len(files) != len(set(files)):
            raise ValueError("Duplicate ZIP entries")
        if not files or files[0] != "mimetype" or z.read("mimetype") != MIME or z.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            raise ValueError("Invalid IDML mimetype entry")
        if z.testzip():
            raise ValueError("IDML ZIP CRC failure")
        for n in files:
            if n.startswith("/") or ".." in Path(n).parts:
                raise ValueError("Unsafe IDML archive path")
        roots = {n: E.fromstring(z.read(n), parser) for n in files if n.endswith(".xml")}
        if any(root.getroottree().docinfo.doctype for root in roots.values()):
            raise ValueError("IDML parts must not contain a DTD")
        if "designmap.xml" not in roots or roots["designmap.xml"].tag != "Document":
            raise ValueError("Missing IDML document manifest")
        ids = set()
        pages = text_frames = images = 0
        content = []
        references = []
        for name, root in roots.items():
            for e in root.iter():
                if e.get("Self"):
                    if e.get("Self") in ids:
                        raise ValueError(f"Duplicate Self ID: {e.get('Self')}")
                    ids.add(e.get("Self"))
                if e.get("src") and e.get("src") not in roots:
                    raise ValueError(f"Missing IDML part: {e.get('src')}")
                for attr in ("ParentStory", "ItemLayer", "AppliedMaster", "PreviousTextFrame", "NextTextFrame", "AppliedObjectStyle", "FillColor", "StrokeColor", "AppliedParagraphStyle", "AppliedCharacterStyle"):
                    ref = e.get(attr)
                    if ref and ref != "n":
                        references.append(ref)
                if e.tag == "Link":
                    uri = urlparse(e.get("LinkResourceURI", ""))
                    if uri.scheme != "file" or not Path(unquote(uri.path)).is_file():
                        raise ValueError(f"Unresolved image link: {e.get('LinkResourceURI')}")
                if e.tag == "Page": pages += 1
                if e.tag == "TextFrame": text_frames += 1
                if e.tag == "Image": images += 1
                if e.tag == "Content": content.append(e.text or "")
        missing = set(references) - ids
        if missing:
            raise ValueError(f"Unresolved IDML references: {sorted(missing)}")
        if not pages:
            raise ValueError("IDML contains no pages")
        return {"pages": pages, "text_frames": text_frames, "images": images, "text_characters": sum(map(len, content)), "xml_parts": len(roots), "structurally_valid": True}
