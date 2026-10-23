#!/usr/bin/env python3
"""Offline validation of the source-fork inputs; does not claim compilation."""
import ast
import json
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
manifest = json.loads((HERE / "upstream.json").read_text())
assert re.fullmatch(r"[0-9a-f]{40}", manifest["commit"])
assert re.fullmatch(r"[0-9a-f]{128}", manifest["firefox"]["sha512"])
assert manifest["firefox"]["version"] in manifest["firefox"]["source_url"]
required = [HERE / path for path in manifest["patches"]] + [
    HERE / "prepare.py", HERE / "build-source.sh", HERE / "package-build.py",
    HERE / "runtime/livara.cfg", HERE / "runtime/livara-autoconfig.js",
    HERE / "overlay/src/livara/LivaraUI.js", HERE / "overlay/src/livara/jar.inc.mn",
    HERE / "overlay/src/livara/LivaraWindowControls.js",
    HERE / "overlay/src/livara/start.xhtml", HERE / "overlay/src/livara/start.js",
    HERE / "overlay/src/livara/start.css", HERE / "overlay/src/livara/livara-glass.css",
    HERE / "LICENSE-MPL-2.0", HERE / "README.md", ROOT / "build/Dockerfile.browser",
    ROOT / "share/livara/browser/livara-browser", ROOT / "share/livara/browser/runtime.py",
    ROOT / "share/livara/browser/official_tor.py", ROOT / "artwork/livara-browser.png",
    ROOT / "fonts/ttf/LivaraSans-Regular.ttf", ROOT / "fonts/ttf/LivaraSans-SemiBold.ttf",
    ROOT / "fonts/ttf/LivaraPersian-Regular.ttf", ROOT / "fonts/ttf/LivaraPersian-SemiBold.ttf",
    ROOT / "fonts/vendor/vazirmatn/OFL.txt", ROOT / "fonts/vendor/vazirmatn/upstream.json",
]
for path in required:
    assert path.is_file() and path.stat().st_size, f"Missing source input: {path}"
for path in list(HERE.glob("*.py")) + list((ROOT / "share/livara/browser").glob("*.py")):
    ast.parse(path.read_text(), filename=str(path))
ElementTree.parse(HERE / "overlay/src/livara/start.xhtml")
for patch in manifest["patches"]:
    assert "diff --git " in (HERE / patch).read_text()
recipe = (ROOT / "build/Dockerfile.browser").read_text()
assert "FROM scratch AS artifact" in recipe
assert "build-source.sh" in recipe
source = (HERE / "build-source.sh").read_text()
for step in ("sha512sum --check", "npm run download", "npm run import", "bootstrap --application-choice browser", "npm run build", "./mach package"):
    assert step in source, f"Missing real source-build step: {step}"
checkout = ROOT / ".build/upstreams/zen"
if (checkout / ".git").is_dir():
    subprocess.run(["python3", str(HERE / "prepare.py"), str(checkout), "--check"], check=True)
print("Livara Browser source inputs, pinned engine, patch metadata and real build recipe validated. Full native compilation is a separate build step.")
