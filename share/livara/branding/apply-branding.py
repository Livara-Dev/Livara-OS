#!/usr/bin/python3
"""Replace distribution identity artwork in an assembled Livara root filesystem.

Only graphics in explicit UI asset locations are changed. Package names, source
attribution, service names, and copyright documentation remain intact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

ROOTS = ("usr/share/icons", "usr/share/pixmaps", "usr/share/plymouth", "usr/share/software-properties")
EXTRA = "usr/share/gnome-shell/extensions/ubuntu-dock@ubuntu.com/media/logo.svg"
REPORT = "usr/share/livara/branding/report.json"
EMPTY_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="260" height="91" viewBox="0 0 260 91"></svg>\n'


def identity_kind(path: Path) -> str | None:
    name = path.name.lower()
    stem = path.stem.lower()
    if path.suffix.lower() not in (".svg", ".png"):
        return None
    # These optional external-service graphics are removed rather than relabeled
    # with Livara's mark; the corresponding service text remains accurate.
    if name.startswith(("ubuntu-pro-logo", "ubuntuone-", "emblem-ubuntuone")):
        return "neutral"
    if stem.startswith(("ubuntu-logo", "distributor-logo", "preferences-ubuntu-panel")):
        return "livara"
    if stem in {"start-here", "start-here-symbolic", "view-app-grid-ubuntu-symbolic", "view-app-grid-ubiquity-symbolic", "ubiquity", "ubiquity-symbolic", "folder-ubuntu"}:
        return "livara"
    if name == "watermark.png" and "plymouth" in path.parts:
        return "livara"
    return None


def candidates(root: Path):
    for relative in ROOTS:
        directory = root / relative
        if not directory.is_dir() or directory.is_symlink():
            continue
        for current, dirs, files in os.walk(directory, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not (Path(current) / d).is_symlink())
            for name in sorted(files):
                path = Path(current) / name
                kind = identity_kind(path)
                if kind:
                    yield path, kind
    extra = root / EXTRA
    if extra.is_file() or extra.is_symlink():
        yield extra, "livara"


def png_bounds(path: Path) -> tuple[int, int]:
    try:
        with path.open("rb") as stream:
            header = stream.read(24)
        if header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR":
            width, height = struct.unpack(">II", header[16:24])
            if 0 < width <= 1024 and 0 < height <= 1024:
                return width, height
    except (OSError, ValueError, struct.error):
        pass
    return 256, 256


def render_png(source: Path, width: int, height: int, neutral: bool = False) -> bytes:
    # Asset compilation happens at build time, with no display or image service.
    # Keeping each original canvas size avoids changing GtkPicture minimum sizes.
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    canvas = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, width, height)
    canvas.fill(0)
    if not neutral:
        image = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(source), width, height, True)
        image.copy_area(0, 0, image.get_width(), image.get_height(), canvas,
                        (width - image.get_width()) // 2, (height - image.get_height()) // 2)
    success, data = canvas.save_to_bufferv("png", [], [])
    if not success:
        raise ValueError("Unable to compile Livara branding PNG")
    return bytes(data)


def apply(root: Path, *, refresh_caches: bool = True, renderer=render_png) -> dict:
    root = root.resolve()
    source_png = root / "usr/share/livara/logo.png"
    source_svg = root / "usr/share/icons/hicolor/scalable/apps/org.livara.Center.svg"
    if not source_png.is_file() or not source_svg.is_file():
        raise ValueError("Install livara-desktop before applying image branding")
    svg = source_svg.read_bytes()
    changes = []
    for path, kind in list(candidates(root)):
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() == ".svg":
            data = svg if kind == "livara" else EMPTY_SVG
        else:
            width, height = png_bounds(path)
            data = renderer(source_png, width, height, kind == "neutral")
        # Replace an alias itself, never follow its target outside this image.
        if path.is_symlink():
            path.unlink()
        path.write_bytes(data)
        path.chmod(0o644)
        changes.append({"path": relative, "kind": kind, "sha256": hashlib.sha256(data).hexdigest()})
    caches = []
    cache_checksums = []
    if refresh_caches:
        command = shutil.which("gtk-update-icon-cache")
        if not command:
            raise ValueError("gtk-update-icon-cache is required to clear cached distribution logos")
        for theme in sorted((root / "usr/share/icons").iterdir()):
            if theme.is_dir() and not theme.is_symlink() and (theme / "index.theme").is_file():
                subprocess.run([command, "--force", "--ignore-theme-index", str(theme)], check=True, capture_output=True)
                caches.append(theme.relative_to(root).as_posix())
                cache = theme / "icon-theme.cache"
                if cache.is_file():
                    cache_checksums.append({"path": cache.relative_to(root).as_posix(),
                                            "sha256": hashlib.sha256(cache.read_bytes()).hexdigest()})
    result = {"schema": 1, "replacements": changes, "icon_caches_rebuilt": caches,
              "icon_caches": cache_checksums,
              "scope": "Known distribution identity graphics; legal notices and service attribution retained"}
    report = root / REPORT
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n")
    return result


def audit(root: Path) -> dict:
    root = root.resolve()
    report = root / REPORT
    if not report.is_file():
        return {"ok": False, "errors": ["Branding report is missing"], "checked": 0}
    data = json.loads(report.read_text())
    if not isinstance(data, dict) or data.get("schema") != 1:
        return {"ok": False, "errors": ["Unsupported branding report"], "checked": 0}
    expected = {entry["path"]: entry["sha256"] for entry in data.get("replacements", [])}
    errors = []
    checked = 0
    for path, kind in candidates(root):
        relative = path.relative_to(root).as_posix()
        checked += 1
        if path.is_symlink():
            errors.append(f"Identity alias was not replaced: {relative}")
        elif relative not in expected:
            errors.append(f"Unprocessed identity graphic: {relative}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected[relative]:
            errors.append(f"Identity graphic changed after branding: {relative}")
    for entry in data.get("icon_caches", []):
        relative = entry["path"]
        cache = root / relative
        if cache.is_symlink() or not cache.is_file():
            errors.append(f"Rebuilt icon cache is missing or aliased: {relative}")
        elif hashlib.sha256(cache.read_bytes()).hexdigest() != entry["sha256"]:
            errors.append(f"Icon cache changed after branding: {relative}")
    return {"ok": not errors, "errors": errors, "checked": checked}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    try:
        result = audit(args.root) if args.audit else apply(args.root)
    except (OSError, ValueError, ImportError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        parser.exit(1, f"Livara branding: {error}\n")
    if args.audit:
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    print(f"Livara branding: {len(result['replacements'])} identity assets replaced; {len(result['icon_caches_rebuilt'])} theme caches rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
