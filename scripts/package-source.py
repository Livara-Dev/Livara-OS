#!/usr/bin/env python3
"""Create the small, reproducible Livara source-builder ZIP; never build an ISO.

Only the explicit source roots used by windows-build.sh are eligible. Files are
stored byte-for-byte, including Build-Livara.bat's CRLF line endings. ZIP order,
timestamps and Unix permission bits do not depend on the source checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import zipfile

SOURCE_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_ROOT = "livara-os"
ARCHIVE_NAME = "livara-os-source-builder.zip"
# Keep this root allowlist aligned with scripts/windows-build.sh.
SOURCE_ENTRIES = (
    "README.md", "LICENSE", "Makefile", "pyproject.toml", ".gitignore",
    ".dockerignore", ".gitattributes", "Build-Livara.bat", "Build-Livara.ps1",
    ".github", "artwork", "build", "docs", "fonts", "forks", "packaging", "scripts", "share",
    "src", "tests",
)
REQUIRED_FILES = (
    "README.md", "LICENSE", "Makefile", "pyproject.toml", ".dockerignore",
    ".gitattributes", "Build-Livara.bat", "Build-Livara.ps1",
    "build/Dockerfile", "build/windows-builder.Dockerfile", "build/assemble.sh", "build/install-forks.py",
    "build/configure-rootfs.sh", "build/verify-graphics-kernel.sh", "build/packages.txt", "build/grub.cfg",
    "packaging/build-deb.sh", "scripts/windows-build.sh", "scripts/package-source.py",
    "scripts/assemble-ci-iso.sh", "scripts/boot-ci-iso.sh",
    "scripts/capture-native-gallery.py", "scripts/settings-ui-smoke.py", "scripts/app-icons-smoke.py",
    "scripts/prepare-code-headers.py", "forks/code/native-headers.json",
    "docs/app-icons.md", "docs/essentials.md", "docs/installation.md",
    "src/livara/essentials.py", "src/livara/essentials_gui.py", "src/livara/theme.py",
    "src/livara/palette.py", "src/livara/install_config.py", "tests/test_essentials.py",
    "scripts/essentials-smoke.py", "scripts/palette-smoke.py", "scripts/desktop-tools-test.cjs",
    "scripts/validate-installer.py", "share/calamares/settings.conf", "share/calamares/job/main.py",
    "share/calamares/livara-install", "share/apt/52livara-security-updates",
    "share/gnome-shell/extensions/livara-glass@livara.local/desktopTools.js",
    "docs/windows-build.md", "docs/window-effects.md", "share/livara/toolbox/Containerfile",
    "src/livara/__init__.py", "src/livara/cli.py", "src/livara/gui.py",
    "src/livara/code_launcher.py", "src/livara/window_style.py", "src/livara/native_controls.py",
    "src/livara/preferences.py", "src/livara/settings_ui.py",
    "src/livara/app_icons.py", "src/livara/app_icons_ui.py", "tests/test_app_icons.py",
    "src/livara/studio.py", "src/livara/studio_gui.py",
    "tests/test_preferences.py", "tests/test_settings_ui.py", "tests/test_studio.py", "tests/test_studio_workspace.py",
    "share/livara/org.livara.desktop.gschema.xml",
    "share/gnome-shell/extensions/livara-glass@livara.local/extension.js",
    "share/gnome-shell/extensions/livara-glass@livara.local/windowEffects.js",
    "build/Dockerfile.code", "build/Dockerfile.browser",
    "scripts/build-code.sh", "scripts/build-browser.sh",
    "forks/code/upstream.json", "forks/browser/upstream.json",
    "forks/browser/prepare-toolchains.py", "forks/browser/toolchains.json",
    "forks/browser/overlay/src/livara/LivaraWindowControls.js",
    "forks/code/test-features.cjs", "forks/code/test-window-controls.mjs",
    "forks/code/overlay/core/livara.contribution.ts", "forks/code/overlay/core/windowControls.ts",
    "forks/code/overlay/extension/package.json", "forks/code/overlay/extension/features.js",
    "forks/code/overlay/onboarding/welcomeOnboarding.contribution.ts",
    "scripts/prepare-tor-browser.py", "forks/tor/upstream.json", "forks/tor/tor-browser-developers.asc",
    "forks/tor/files.json", "forks/tor/bundle.sig.asc", "forks/tor/download-linux-x86_64.json",
    "forks/tor/sha256sums-signed-build.txt",
    "scripts/build-fonts.py", "tests/test_fonts.py", "fonts/sources/design.json", "fonts/OFL.txt",
    "artwork/livara-logo.png", "artwork/livara-browser.png",
    "artwork/livara-code.png", "artwork/org.livara.Code.svg",
    "share/applications/org.livara.Code.desktop", "share/applications/org.livara.Browser.desktop",
    "artwork/org.livara.Browser.svg", "share/livara/browser/livara-browser",
    "share/livara/browser/official_tor.py",
    "fonts/vendor/vazirmatn/OFL.txt", "fonts/vendor/vazirmatn/upstream.json",
    "fonts/vendor/vazirmatn/Vazirmatn-Variable.ttf",
    "fonts/vendor/vazirmatn/sources/Vazirmatn-Regular.sfd",
    "fonts/vendor/vazirmatn/sources/Vazirmatn-Thin.sfd",
    "fonts/vendor/vazirmatn/sources/Vazirmatn-Black.sfd",
    "fonts/ttf/LivaraPersian-Regular.ttf", "fonts/ttf/LivaraPersian-SemiBold.ttf",
    "fonts/sources/LivaraPersian-Regular.ttx", "fonts/sources/LivaraPersian-SemiBold.ttx",
) + tuple(
    name
    for face in ("LivaraSans-Regular", "LivaraSans-SemiBold", "LivaraMono-Regular", "LivaraMono-SemiBold")
    for name in (
        f"fonts/ttf/{face}.ttf",
        f"fonts/sources/{face}.ufo/fontinfo.plist",
        f"fonts/sources/{face}.ufo/metainfo.plist",
        f"fonts/sources/{face}.ufo/layercontents.plist",
        f"fonts/sources/{face}.ufo/glyphs/contents.plist",
    )
)
EXCLUDED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", ".build", "dist", "__pycache__", "node_modules",
    ".cache", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    ".venv", "venv", ".npm", ".yarn", ".mozbuild",
    ".ssh", ".gnupg", ".aws", ".azure", ".docker",
    ".kube", ".config", ".codex", "credentials", "secrets", ".secrets",
})
EXCLUDED_FILES = frozenset({
    ".env", ".netrc", "_netrc", ".npmrc", ".pypirc", "credentials.json",
    "service-account.json", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    ".ds_store", "thumbs.db",
})
EXCLUDED_PATHS = frozenset({"docs/livara-desktop.png"})
SECRET_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".jks")
PAYLOAD_SUFFIXES = (
    ".iso", ".deb", ".udeb", ".squashfs", ".img", ".vhd", ".vhdx",
    ".vmdk", ".qcow2", ".tar", ".tar.gz", ".tar.xz", ".tar.zst", ".tgz",
)
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_SOURCE_BYTES = 128 * 1024 * 1024
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
WINDOWS_RESERVED = frozenset({"con", "prn", "aux", "nul"} | {
    f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
})


class SourceError(ValueError):
    """The input cannot produce a complete source-only builder archive."""


def excluded(path: PurePosixPath) -> bool:
    parts = tuple(part.lower() for part in path.parts)
    name = parts[-1]
    return (
        any(part in EXCLUDED_DIRECTORIES or part.endswith(".egg-info") for part in parts)
        or (parts[0] == "forks" and any(part in ("vendor", "third_party") for part in parts))
        or path.as_posix().lower() in EXCLUDED_PATHS
        or name in EXCLUDED_FILES
        or name.startswith(".env.")
        or name.endswith((".pyc", ".pyo", ".log", "~") + SECRET_SUFFIXES)
    )


def validate_relative_path(path: PurePosixPath) -> None:
    if path.is_absolute() or not path.parts or path.parts[0] not in SOURCE_ENTRIES:
        raise SourceError(f"Path is outside the source allowlist: {path}")
    for part in path.parts:
        if (
            part in (".", "..") or part.endswith((".", " "))
            or any(character in part for character in '<>:"\\|?*')
            or any(ord(character) < 32 for character in part)
            or part.split(".", 1)[0].lower() in WINDOWS_RESERVED
        ):
            raise SourceError(f"Path cannot be extracted safely on Windows: {path}")
    name = path.name.lower()
    if name.endswith(PAYLOAD_SUFFIXES) or ".iso." in name or name.startswith("kali-core"):
        raise SourceError(f"Built payload is forbidden in the source archive: {path}")


def collect_sources(root: Path) -> list[Path]:
    files: list[Path] = []
    total = 0
    portable_names: set[str] = set()

    def visit(path: Path) -> None:
        nonlocal total
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if excluded(relative):
            return
        validate_relative_path(relative)
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise SourceError(f"Source symlinks are not portable to Windows: {relative}")
        portable = relative.as_posix().casefold()
        if portable in portable_names:
            raise SourceError(f"Duplicate Windows path: {relative}")
        portable_names.add(portable)
        if stat.S_ISDIR(info.st_mode):
            for child in sorted(path.iterdir(), key=lambda item: item.name):
                visit(child)
        elif stat.S_ISREG(info.st_mode):
            if info.st_size > MAX_FILE_BYTES:
                raise SourceError(f"Source file exceeds 32 MiB: {relative}")
            total += info.st_size
            if total > MAX_SOURCE_BYTES:
                raise SourceError("Source exceeds 128 MiB; remove generated products first.")
            files.append(path)
        else:
            raise SourceError(f"Source must contain only regular files: {relative}")

    for name in SOURCE_ENTRIES:
        candidate = root / name
        if candidate.exists() or candidate.is_symlink():
            visit(candidate)
    included = {path.relative_to(root).as_posix(): path for path in files}
    missing = [name for name in REQUIRED_FILES if name not in included or not included[name].stat().st_size]
    if missing:
        raise SourceError("Required source is missing or empty: " + ", ".join(missing))
    batch = included["Build-Livara.bat"].read_bytes()
    if b"\r\n" not in batch or b"\n" in batch.replace(b"\r\n", b""):
        raise SourceError("Build-Livara.bat must retain Windows CRLF line endings.")
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def source_mode(path: Path, payload: bytes) -> int:
    # Shell files and executable scripts retain useful permissions on Linux;
    # all other files use 0644 even if their checkout was created with mode 0600.
    return 0o755 if path.suffix == ".sh" or payload.startswith(b"#!") else 0o644


def audit_archive(archive_path: Path) -> tuple[int, int]:
    with zipfile.ZipFile(archive_path) as archive:
        names: set[str] = set()
        portable_paths: dict[str, tuple[str, bool]] = {}
        total = 0
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            if len(path.parts) < 2 or path.parts[0] != ARCHIVE_ROOT or entry.is_dir():
                raise SourceError(f"Unexpected ZIP entry: {entry.filename}")
            relative = PurePosixPath(*path.parts[1:])
            validate_relative_path(relative)
            if excluded(relative) or entry.filename in names:
                raise SourceError(f"Excluded or duplicate ZIP entry: {entry.filename}")
            # ZIPs omit directory entries, but Windows still needs unambiguous
            # case-insensitive paths for every directory and final filename.
            for depth in range(1, len(relative.parts) + 1):
                prefix = PurePosixPath(*relative.parts[:depth]).as_posix()
                key = prefix.casefold()
                is_file = depth == len(relative.parts)
                previous = portable_paths.get(key)
                if previous is not None and (previous != (prefix, is_file) or is_file):
                    raise SourceError(f"Conflicting Windows ZIP path: {entry.filename}")
                portable_paths[key] = (prefix, is_file)
            names.add(entry.filename)
            if entry.file_size > MAX_FILE_BYTES or entry.flag_bits & 1:
                raise SourceError(f"Oversized or encrypted ZIP entry: {entry.filename}")
            mode = entry.external_attr >> 16
            if stat.S_IFMT(mode) != stat.S_IFREG or stat.S_IMODE(mode) not in (0o644, 0o755):
                raise SourceError(f"Unexpected ZIP permissions: {entry.filename}")
            total += entry.file_size
        if total > MAX_SOURCE_BYTES:
            raise SourceError("ZIP contains too much uncompressed source.")
        if any(f"{ARCHIVE_ROOT}/{name}" not in names for name in REQUIRED_FILES):
            raise SourceError("ZIP is missing required builder or editor files.")
        bad = archive.testzip()
        if bad:
            raise SourceError(f"ZIP checksum failed: {bad}")
        return len(names), total


def build_archive(root: Path, output_dir: Path) -> Path:
    files = collect_sources(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / ARCHIVE_NAME
    descriptor, temporary_name = tempfile.mkstemp(prefix=".livara-source-", suffix=".zip", dir=output_dir)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in files:
                before = path.stat()
                payload = path.read_bytes()
                after = path.stat()
                if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                    raise SourceError(f"Source changed while packaging: {path.relative_to(root)}")
                relative = path.relative_to(root).as_posix()
                entry = zipfile.ZipInfo(f"{ARCHIVE_ROOT}/{relative}", date_time=ZIP_TIMESTAMP)
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | source_mode(path, payload)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, payload, compresslevel=9)
        count, source_bytes = audit_archive(temporary)
        with temporary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        temporary.chmod(0o644)
        temporary.replace(destination)
        checksum = destination.with_name(destination.name + ".sha256")
        checksum.write_text(f"{digest}  {destination.name}\n", encoding="ascii")
        checksum.chmod(0o644)
        print(f"Created {destination} ({destination.stat().st_size:,} bytes).")
        print(f"Audited {count} source files ({source_bytes:,} uncompressed bytes); no ISO or package payloads.")
        print(f"SHA-256: {digest}")
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate the source set without writing an archive")
    parser.add_argument("--output-dir", type=Path, default=SOURCE_ROOT / "dist", help="output directory (default: dist)")
    options = parser.parse_args()
    try:
        if options.check:
            files = collect_sources(SOURCE_ROOT)
            print(f"Source package check passed: {len(files)} files; no archive or ISO created.")
        else:
            build_archive(SOURCE_ROOT, options.output_dir.resolve())
    except (OSError, SourceError, zipfile.BadZipFile) as error:
        print(f"Source packaging failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
