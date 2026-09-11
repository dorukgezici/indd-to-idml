from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from . import __version__
from .convert import convert_psd
from .idml import validate
from .indd import inspect_indd
from .fonts import installed_postscript_names

ROOT = Path(__file__).resolve().parent


def parser():
    p = argparse.ArgumentParser(description="Convert INDD files to editable IDML using a local Photopea browser engine. Reconstruction has fidelity limitations; see each report.")
    p.add_argument("input", nargs="?", type=Path, default=Path("in"), help="INDD file or directory to scan recursively (default: in)")
    p.add_argument("-o", "--output", type=Path, default=Path("out"), help="output directory (default: out)")
    p.add_argument("--force", action="store_true", help="replace existing generated outputs")
    p.add_argument("--timeout", type=int, default=300, help="conversion engine timeout per file in seconds")
    p.add_argument("--intermediate", type=Path, help="use an existing Photopea PSD, for a single INDD input")
    p.add_argument("--cache-dir", type=Path, default=Path(".cache/indd-to-idml"))
    p.add_argument("--validate", type=Path, metavar="FILE.idml", help="validate an existing IDML and all linked images")
    p.add_argument("--inspect", action="store_true", help="inspect INDD versions and advisory metadata without conversion")
    p.add_argument("--version", action="version", version=__version__)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.validate:
        try: print(json.dumps(validate(args.validate.resolve()), indent=2)); return 0
        except Exception as e: print(f"Invalid IDML: {e}", file=sys.stderr); return 1
    source = args.input.resolve()
    if not source.exists():
        print(f"Input not found: {source}", file=sys.stderr); return 1
    files = [source] if source.is_file() else sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() == ".indd")
    if not files:
        print("No INDD files found", file=sys.stderr); return 1
    if args.intermediate and len(files) != 1:
        print("--intermediate requires one INDD file", file=sys.stderr); return 1
    if args.timeout < 1:
        print("--timeout must be positive", file=sys.stderr); return 1
    base = source.parent if source.is_file() else source
    out = args.output.resolve()
    if out == source or (source.is_dir() and out.is_relative_to(source)):
        print("Output must be outside the input directory", file=sys.stderr); return 1
    failures = 0; converted = []
    available_fonts = installed_postscript_names() if not args.inspect else set()
    for f in files:
        try:
            metadata = inspect_indd(f)
            if args.inspect:
                print(json.dumps(metadata, ensure_ascii=False, indent=2)); continue
            relative = f.relative_to(base).with_suffix(".idml")
            dest = out / relative
            if dest.exists() and not args.force:
                raise ValueError(f"Output already exists: {dest}. Use --force to replace it.")
            dest.parent.mkdir(parents=True, exist_ok=True)
            cached = args.cache_dir.resolve() / (metadata["sha256"] + ".psd")
            intermediate = args.intermediate.resolve() if args.intermediate else cached
            if args.intermediate is None and not intermediate.exists():
                cached.parent.mkdir(parents=True, exist_ok=True)
                bridge = ROOT / "photopea.mjs"
                if shutil.which("node") is None:
                    raise ValueError("Node.js is required for the browser engine")
                print(f"Reading {f.name}...", file=sys.stderr, flush=True)
                temporary = cached.with_suffix(".partial.psd")
                try:
                    subprocess.run(["node", str(bridge), str(f), str(temporary), str(args.timeout)], check=True, timeout=args.timeout + 30)
                    temporary.replace(cached)
                finally:
                    temporary.unlink(missing_ok=True)
            print(f"Writing {relative}...", file=sys.stderr, flush=True)
            # Keep an existing IDML intact if reconstruction or validation fails.
            temp_idml = dest.with_suffix(".partial.idml")
            try:
                report = convert_psd(intermediate, f, temp_idml, metadata)
                if hashlib.sha256(f.read_bytes()).hexdigest() != metadata["sha256"]:
                    raise ValueError("Input changed during conversion")
                temp_idml.replace(dest)
            finally:
                temp_idml.unlink(missing_ok=True)
            report["output"] = str(dest)
            report["missing_fonts"] = [f["postscript"] for f in report["fonts"] if f["postscript"] not in available_fonts]
            if report["missing_fonts"]:
                report["warnings"].append("Install the original fonts to avoid substitution: " + ", ".join(report["missing_fonts"]))
            report_file = dest.with_suffix(".report.json")
            report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            v = report["validation"]
            print(f"{relative}: {v['pages']} pages, {v['text_frames']} editable text frames, {v['images']} images; {report['restored_original_images']} originals restored")
            for warning in report["warnings"]: print(f"  Warning: {warning}", file=sys.stderr)
            converted.append(str(dest))
        except (Exception, KeyboardInterrupt) as e:
            failures += 1
            print(f"Failed {f.name}: {e}", file=sys.stderr)
            if isinstance(e, KeyboardInterrupt): return 130
    if not args.inspect:
        print(f"Converted {len(converted)}/{len(files)}. Reports identify reconstruction limits.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
