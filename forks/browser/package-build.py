#!/usr/bin/env python3
"""Stage only an actual compiled Livara binary and its engine resources."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent


def package(dist: Path, output: Path) -> Path:
    compiled = dist / "livara-browser"
    binary = compiled / "livara-browser"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError("The full source build did not produce dist/livara-browser/livara-browser")
    with binary.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise ValueError("The browser artifact must contain a compiled Linux ELF binary")
    if not (compiled / "libxul.so").is_file():
        raise ValueError("The compiled Gecko engine is missing")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="livara-browser-package-", dir=output) as temporary:
        root = Path(temporary) / "livara-browser"
        # Resolve build-tree symlinks so the installed archive never depends
        # on paths inside the compiler/object cache.
        shutil.copytree(compiled, root, symlinks=False)
        (root / "defaults/pref").mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / "runtime/livara-autoconfig.js", root / "defaults/pref/livara-autoconfig.js")
        shutil.copy2(HERE / "runtime/livara.cfg", root / "livara.cfg")
        shutil.copy2(HERE / "LICENSE-MPL-2.0", root / "LICENSE-Livara-fork-MPL-2.0")
        shutil.copy2(HERE.parents[1] / "LICENSE", root / "LICENSE-Livara-chrome-GPL-3.0")
        shutil.copy2(HERE.parents[1] / "fonts/OFL.txt", root / "LICENSE-Livara-fonts-OFL.txt")
        shutil.copy2(HERE.parents[1] / "fonts/vendor/vazirmatn/OFL.txt", root / "LICENSE-Livara-Persian-Vazirmatn-OFL.txt")
        shutil.copy2(HERE.parents[1] / "fonts/vendor/vazirmatn/upstream.json", root / "livara-persian-upstream.json")
        shutil.copy2(HERE / "README.md", root / "LIVARA-SOURCE-NOTICE.md")
        source_manifest = dist.parents[1].parent / "livara-source-manifest.json"
        if not source_manifest.is_file():
            raise ValueError("The pinned source preparation manifest is missing")
        shutil.copy2(source_manifest, root / "livara-source-manifest.json")
        # A native engine exists before the archive is accepted; a script that
        # launches a stock Zen download cannot meet these package checks.
        version = subprocess.run([str(binary), "--version"], text=True, capture_output=True, check=True).stdout.strip()
        if "Livara" not in version or "Zen" in version:
            raise ValueError(f"Unexpected compiled browser identity: {version}")
        identity = {"schema": 1, "compiled_version": version,
                    "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                    "upstream": json.loads((HERE / "upstream.json").read_text())}
        (root / "livara-build.json").write_text(json.dumps(identity, indent=2) + "\n")
        # Compile-time Jar manifests omitted the registered Zen Fluent files.
        # Seal the same maintained resources used by incremental updates into
        # every new browser package, before calculating its archive checksum.
        sys.path.insert(0, str(HERE.parents[1] / "src"))
        from livara.app_updates import browser_source_plan, atomic_write
        for path, _previous, fresh in browser_source_plan(root, HERE.parents[1]):
            atomic_write(path, fresh)
        artifact = output / "livara-browser-linux-x64.tar.xz"
        staged = Path(temporary) / artifact.name
        with tarfile.open(staged, "w:xz", preset=3) as archive:
            for path in [root, *sorted(root.rglob("*"))]:
                info = archive.gettarinfo(str(path), arcname=str(path.relative_to(root.parent)))
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                info.mode = 0o755 if path.is_dir() or os.access(path, os.X_OK) else 0o644
                if info.isfile():
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
                else:
                    archive.addfile(info)
        os.replace(staged, artifact)
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        (output / (artifact.name + ".sha256")).write_text(f"{digest}  {artifact.name}\n")
        return artifact


if __name__ == "__main__":
    print(package(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))
