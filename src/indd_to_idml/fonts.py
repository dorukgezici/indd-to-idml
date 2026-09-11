"""Report available fonts without substituting document typography."""
from pathlib import Path
import sys
from fontTools.ttLib import TTFont, TTCollection, TTLibError


def installed_postscript_names():
    roots = [Path.home() / ".local/share/fonts", Path("/usr/share/fonts")]
    if sys.platform == "darwin":
        roots = [Path.home() / "Library/Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts")]
        # Font Book downloads live in versioned MobileAsset stores.
        roots.extend(Path("/System/Library/AssetsV2").glob("com_apple_MobileAsset_Font[0-9]*"))
    elif sys.platform == "win32":
        import os
        roots = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]
    names = set()
    for root in roots:
        for file in root.rglob("*") if root.exists() else []:
            if file.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
                continue
            try:
                if file.suffix.lower() == ".ttc":
                    fonts = TTCollection(file, lazy=True).fonts
                else:
                    fonts = [TTFont(file, lazy=True)]
                for font in fonts:
                    names.update(n.toUnicode() for n in font["name"].names if n.nameID == 6)
                    font.close()
            except (OSError, ValueError, KeyError, TTLibError):
                pass
    return names
