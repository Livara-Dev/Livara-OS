"""Refresh only Livara-owned resources in the matching installed source forks.

The browser engine, executable, profiles, Code extensions and user preferences
are never replaced. Original files are retained for recovery before each change.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile

BEGIN = "/* BEGIN LIVARA DESKTOP UPDATE */"
END = "/* END LIVARA DESKTOP UPDATE */"
BROWSER_RESOURCES = ("LivaraUI.js", "LivaraWindowControls.js", "start.js", "livara-glass.css", "start.css")
BROWSER_LOCALES = ("branding/brand.ftl", "browser/preferences/zen-preferences.ftl", *(
    "browser/" + name + ".ftl" for name in (
        "zen-boosts", "zen-command-palette", "zen-folders", "zen-general", "zen-library",
        "zen-live-folders", "zen-menubar", "zen-share", "zen-space-routing", "zen-split-view",
        "zen-vertical-tabs", "zen-welcome", "zen-workspaces")))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    """Do not traverse administrator-installed links or edit unexpected files."""
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError(f"Refusing symbolic link: {path}")
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"Expected a regular file: {path}")
    return path.read_bytes()


def atomic_write(path, data):
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, name = tempfile.mkstemp(prefix=".livara-resource-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def browser_plan(app, payload, pin):
    identity = json.loads(regular(app / "livara-build.json"))
    if identity.get("upstream", {}).get("commit") != pin:
        raise ValueError("Installed Browser is a different source build; resources were preserved")
    if digest(regular(app / "livara-browser")) != identity.get("binary_sha256"):
        raise ValueError("Installed Browser executable does not match its build manifest")
    replacements = {name: regular(payload / "browser" / name) for name in BROWSER_RESOURCES}
    locales = {"localization/en-US/" + name: regular(payload / "browser/locales/en-US" / name)
               for name in BROWSER_LOCALES}
    counts = dict.fromkeys(replacements, 0)
    plans = []
    for path in (app / "browser/omni.ja", app / "omni.ja"):
        if not path.exists():
            continue
        original = regular(path)
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original)) as source:
            entries = source.namelist()
            if len(set(entries)) != len(entries):
                raise ValueError("Duplicate browser archive entries; resource update refused")
            changes = {}
            for name, fresh in replacements.items():
                matches = [entry for entry in entries if entry.endswith("/livara/" + name)]
                counts[name] += len(matches)
                changes.update({entry: fresh for entry in matches})
            # Zen's registered Fluent resources were absent from the compiled
            # package. One missing resource prevents the whole browser window's
            # localization bundle from resolving, including native menu labels.
            if any(entry.endswith("/livara/LivaraUI.js") for entry in entries):
                changes.update(locales)
            if not any(entry not in entries or source.read(entry) != fresh for entry, fresh in changes.items()):
                continue
            with zipfile.ZipFile(output, "w") as target:
                for info in source.infolist():
                    if info.filename.startswith(("jsloader/", "jssubloader/")):
                        continue
                    target.writestr(info, changes.get(info.filename, source.read(info.filename)))
                for entry, fresh in changes.items():
                    if entry not in entries:
                        target.writestr(entry, fresh, compress_type=zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(io.BytesIO(output.getvalue())) as check:
            if check.testzip() is not None:
                raise ValueError("Updated browser archive failed its integrity check")
        plans.append((path, original, output.getvalue()))
    if any(count != 1 for count in counts.values()):
        raise ValueError("Expected exactly one copy of each maintained Browser resource")
    return plans


def browser_source_plan(app, repository):
    """Use the installed updater's exact planner for fresh builds and CI."""
    pin = json.loads(regular(repository / 'forks/browser/upstream.json'))['commit']
    with tempfile.TemporaryDirectory(prefix='livara-browser-payload-') as folder:
        payload = Path(folder)
        for name in BROWSER_RESOURCES:
            target = payload / 'browser' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(regular(repository / 'forks/browser/overlay/src/livara' / name))
        for name in BROWSER_LOCALES:
            target = payload / 'browser/locales/en-US' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(regular(repository / 'forks/browser/locales/en-US' / name))
        return browser_plan(app, payload, pin)


def code_plan(app, payload, pin):
    identity = json.loads(regular(app / "resources/app/livara-build.json"))
    if identity.get("upstream", {}).get("commit") != pin or identity.get("distribution") != "Livara Code":
        raise ValueError("Installed Code is a different source build; resources were preserved")
    if identity.get("desktop_package_version") == json.loads(regular(payload / "manifest.json"))["version"]:
        # This release's separately compiled DEB already includes the material
        # and controller. Keep its package-owned files byte-identical.
        return []
    path = app / "resources/app/out/vs/workbench/workbench.desktop.main.css"
    original = regular(path)
    text = original.decode("utf-8")
    if (text.count(BEGIN), text.count(END)) not in ((0, 0), (1, 1)):
        raise ValueError("Damaged Code update markers; stylesheet was preserved")
    if BEGIN in text:
        start, finish = text.index(BEGIN), text.index(END)
        if start > finish:
            raise ValueError("Reversed Code update markers; stylesheet was preserved")
        text = text[:start] + text[finish + len(END):]
    fresh = (text.rstrip() + "\n" + BEGIN + "\n" + regular(payload / "code/livara.css").decode("utf-8").rstrip() + "\n" + END + "\n").encode()
    plans = [(path, original, fresh)] if fresh != original else []
    # Code's integrity checker hashes the shipped workbench CSS. Keep its
    # existing checksum entry consistent instead of disabling that checker.
    product_path = app / "resources/app/product.json"
    if product_path.exists():
        original_product = regular(product_path)
        product = json.loads(original_product)
        checksums = product.get("checksums", {})
        key = "vs/workbench/workbench.desktop.main.css"
        if key in checksums:
            previous_checksum = base64.b64encode(hashlib.sha256(original).digest()).decode().rstrip("=")
            if checksums[key] != previous_checksum:
                raise ValueError("Installed Code stylesheet fails its original integrity checksum; preserved")
            checksum = base64.b64encode(hashlib.sha256(fresh).digest()).decode().rstrip("=")
            if checksums[key] != checksum:
                checksums[key] = checksum
                plans.append((product_path, original_product, (json.dumps(product, indent=2) + "\n").encode()))
    return plans


def refresh(*, opt=Path("/opt"), payload=Path("/usr/share/livara/app-resources"), backup=Path("/var/lib/livara/app-resource-backups")):
    manifest = json.loads(regular(payload / "manifest.json"))
    plans, results = [], []
    # Validate every installed component before writing any of them.
    for name, planner, key in (("livara-browser", browser_plan, "browser_commit"), ("livara-code", code_plan, "code_commit")):
        app = opt / name
        if not app.exists():
            results.append({"app": name, "status": "not-installed"})
            continue
        component = planner(app, payload, manifest[key])
        plans.extend(component)
        results.append({"app": name, "status": "updated" if component else "current", "files": [str(p) for p, _, _ in component]})
    if plans:
        if any(parent.is_symlink() for parent in (backup, *backup.parents)):
            raise ValueError("Refusing linked backup directory")
        backup.mkdir(parents=True, exist_ok=True, mode=0o700)
        for path, previous, _ in plans:
            saved = backup / (digest(str(path).encode())[:16] + "-" + digest(previous))
            if saved.exists():
                if regular(saved) != previous:
                    raise ValueError("Existing recovery backup has unexpected contents")
            else:
                atomic_write(saved, previous)
        applied = []
        report_path = backup / "latest.json"
        if report_path.exists() or report_path.is_symlink():
            regular(report_path)
        record = {"version": manifest["version"], "results": results,
                  "files": [{"path": str(path), "before_sha256": digest(previous), "after_sha256": digest(fresh)} for path, previous, fresh in plans]}
        try:
            for path, previous, fresh in plans:
                atomic_write(path, fresh)
                applied.append((path, previous))
            atomic_write(report_path, (json.dumps(record, indent=2) + "\n").encode())
        except Exception:
            for path, previous in reversed(applied):
                atomic_write(path, previous)
            raise
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run sudo livara-refresh-app-resources after closing Browser and Code")
    try:
        print(json.dumps(refresh(), indent=2))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"Livara application resources were not updated: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
