#!/usr/bin/env python3
"""Apply Livara's source fork to the exact pinned upstream checkout.

This changes the source compiled by Surfer/mach, rather than injecting a user
profile into an upstream browser binary. Source and asset inputs are reported.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def git(checkout: Path, *args: str, check: bool = True):
    return subprocess.run(["git", "-C", str(checkout), *args], check=check,
                          text=True, capture_output=True)


def validate(checkout: Path) -> dict:
    manifest = json.loads((HERE / "upstream.json").read_text())
    revision = git(checkout, "rev-parse", "HEAD").stdout.strip()
    if revision != manifest["commit"]:
        raise ValueError(f"Expected pinned Zen commit {manifest['commit']}; found {revision}")
    source = json.loads((checkout / "surfer.json").read_text())
    if source["version"]["version"] != manifest["firefox"]["version"]:
        raise ValueError("The Firefox engine version does not match the pinned source manifest")
    lock = json.loads((checkout / "package-lock.json").read_text())
    if lock["packages"]["node_modules/@zen-browser/surfer"]["version"] != manifest["surfer"]:
        raise ValueError("Unexpected Surfer build tool version")
    for patch in manifest["patches"]:
        path = str(HERE / patch)
        forward = git(checkout, "apply", "--check", path, check=False)
        reverse = git(checkout, "apply", "--reverse", "--check", path, check=False)
        if forward.returncode and reverse.returncode:
            raise ValueError(f"The source patch does not apply cleanly: {patch}\n{forward.stderr}")
    return manifest


def rebrand_locales(checkout: Path) -> int:
    """Change visible Fluent text; preserve message IDs and comment attribution."""
    count = 0
    for root in (checkout / "locales", checkout / "src"):
        for path in root.rglob("*.ftl"):
            lines = path.read_text().splitlines(keepends=True)
            updated = []
            for line in lines:
                if not line.lstrip().startswith("#"):
                    # A message ID before '=' is an API, not product copy.
                    prefix, separator, value = line.partition("=")
                    if separator:
                        line = prefix + separator + re.sub(r"\bZen(?: Browser)?\b", "Livara Browser", value)
                    elif line.startswith((" ", "\t")):
                        line = re.sub(r"\bZen(?: Browser)?\b", "Livara Browser", line)
                updated.append(line)
            output = "".join(updated)
            if output != "".join(lines):
                path.write_text(output)
                count += 1
    return count


def branding(checkout: Path) -> None:
    from PIL import Image

    folder = checkout / "configs/branding/release"
    for name in ("release", "twilight"):
        path = checkout / "configs/branding" / name
        if path.exists():
            shutil.rmtree(path)
    content = folder / "content"
    content.mkdir(parents=True)
    original = ROOT / "artwork/livara-browser.png"
    image = Image.open(original).convert("RGBA")
    for size in (16, 22, 24, 32, 48, 64, 128, 256, 512, 1024):
        image.resize((size, size), Image.Resampling.LANCZOS).save(folder / f"logo{size}.png")
        image.resize((size, size), Image.Resampling.LANCZOS).save(content / f"icon{size}.png")
    for name in ("logo.png", "logo-mac.png"):
        image.resize((1024, 1024), Image.Resampling.LANCZOS).save(folder / name)
    for name in ("firefox.ico", "firefox64.ico", "pbmode.ico"):
        image.save(folder / name, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    image.save(content / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    for name, size in (("about-logo.png", 512), ("about-logo@2x.png", 1024),
                       ("about-logo-private.png", 512), ("about-logo-private@2x.png", 1024)):
        image.resize((size, size), Image.Resampling.LANCZOS).save(content / name)
    embedded = base64.b64encode(original.read_bytes()).decode("ascii")
    logo = f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512"><image width="512" height="512" href="data:image/png;base64,{embedded}"/></svg>\n'
    wordmark = '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="80"><text x="2" y="58" fill="#d6b8ff" font-family="Livara Sans,sans-serif" font-size="54" font-weight="600">Livara Browser</text></svg>\n'
    for name in ("about-logo.svg", "about-logo-private.svg"):
        (content / name).write_text(logo)
    for name in ("about-wordmark.svg", "firefox-wordmark.svg"):
        (content / name).write_text(wordmark)
    destination = checkout / "src/livara"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, destination / "livara-browser.png")
    fonts = destination / "fonts"
    fonts.mkdir(exist_ok=True)
    for name in ("LivaraSans-Regular.ttf", "LivaraSans-SemiBold.ttf", "LivaraPersian-Regular.ttf", "LivaraPersian-SemiBold.ttf"):
        source = ROOT / "fonts/ttf" / name
        if not source.is_file():
            raise ValueError(f"Required Livara font is missing: {source}")
        shutil.copy2(source, fonts / name)


def prepare(checkout: Path, check_only: bool = False) -> dict:
    manifest = validate(checkout)
    if check_only:
        return {"commit": manifest["commit"], "patches_valid": True}
    for patch in manifest["patches"]:
        path = str(HERE / patch)
        if git(checkout, "apply", "--check", path, check=False).returncode == 0:
            git(checkout, "apply", path)
    overlay = HERE / "overlay"
    if not (overlay / "src/livara/LivaraUI.js").is_file():
        raise ValueError("The compiled Livara chrome overlay is missing")
    shutil.copytree(overlay, checkout, dirs_exist_ok=True)
    branding(checkout)
    locales = rebrand_locales(checkout)
    # Source configuration appended by Surfer to the generated engine mozconfig.
    shutil.copy2(HERE / "mozconfig", checkout / "mozconfig")
    report = {"schema": 1, "upstream": manifest, "localized_files_changed": locales,
              "patch_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                               for name in manifest["patches"]},
              "overlay_sha256": {str(path.relative_to(overlay)): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sorted(overlay.rglob("*")) if path.is_file()},
              "locale_sha256": {str(path.relative_to(HERE / 'locales')): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in sorted((HERE / 'locales').rglob('*.ftl'))},
              "source_inputs": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (ROOT / "artwork/livara-browser.png", ROOT / "fonts/ttf/LivaraSans-Regular.ttf", ROOT / "fonts/ttf/LivaraSans-SemiBold.ttf", ROOT / "fonts/ttf/LivaraPersian-Regular.ttf", ROOT / "fonts/ttf/LivaraPersian-SemiBold.ttf")}}
    (checkout / "livara-source-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--check", action="store_true", help="verify revision and patch application without changing files")
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.checkout.resolve(), args.check), indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
