#!/usr/bin/env python3
"""Verify and stage a pinned, unchanged official Tor Browser Linux bundle.

Usage: prepare-tor-browser.py OUTPUT_DIRECTORY [--archive LOCAL_ARCHIVE]
       prepare-tor-browser.py --check
The offline check validates pin assets and the primary public-key fingerprint;
it downloads nothing. The complete step requires Python 3, gpg and gpgv.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import ssl
import struct
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "forks/tor"
ARTIFACT = "livara-tor-browser-linux-x64.tar.xz"
PRIMARY = "EF6E286DDA85EA2A4BA7DE684E2C6E8793298290"
MAX_DOWNLOAD = 512 * 1024 * 1024


def sha256(filename: Path) -> str:
    digest = hashlib.sha256()
    with filename.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def key_fingerprint(key: Path, gpg: str) -> str:
    with tempfile.TemporaryDirectory(prefix="livara-tor-key-") as temporary:
        result = subprocess.run([gpg, "--no-options", "--homedir", temporary, "--batch", "--with-colons", "--show-keys", str(key)],
                                check=True, capture_output=True, text=True)
    primaries, current = [], None
    for line in result.stdout.splitlines():
        fields = line.split(":")
        if fields[0] in ("pub", "sub"):
            current = fields[0]
        elif fields[0] == "fpr" and current == "pub":
            primaries.append(fields[9]); current = None
    if primaries != [PRIMARY]:
        raise ValueError("The Tor Browser public key does not match the pinned primary fingerprint")
    return primaries[0]


def check_pin(pin: Path = PIN) -> dict:
    data = json.loads((pin / "upstream.json").read_text())
    if data.get("schema") != 1 or data.get("primary_fingerprint") != PRIMARY:
        raise ValueError("Unsupported Tor Browser pin or signing identity")
    version = data.get("version", "")
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)*", version):
        raise ValueError("Pin a stable Tor Browser version")
    expected_url = f"https://dist.torproject.org/torbrowser/{version}/tor-browser-linux-x86_64-{version}.tar.xz"
    if data.get("archive_url") != expected_url or data.get("signature_url") != expected_url + ".asc":
        raise ValueError("The archive must use its pinned official Tor Project release URL")
    if not re.fullmatch(r"[0-9a-f]{64}", data.get("sha256", "")):
        raise ValueError("Missing pinned bundle SHA-256")
    required = {"tor-browser-developers.asc", "bundle.sig.asc", "download-linux-x86_64.json", "sha256sums-signed-build.txt", "files.json"}
    assets = data.get("assets", {})
    if set(assets) != required:
        raise ValueError("Incomplete Tor Browser provenance assets")
    for name, digest in assets.items():
        source = pin / name
        if source.is_symlink() or not source.is_file() or source.stat().st_size > 2 * 1024 * 1024 or sha256(source) != digest:
            raise ValueError(f"Pinned Tor Browser asset changed: {name}")
    metadata = json.loads((pin / "download-linux-x86_64.json").read_text())
    if any(metadata.get(key) != data.get(target) for key, target in (("version", "version"), ("binary", "archive_url"), ("sig", "signature_url"))):
        raise ValueError("Official download metadata differs from the pin")
    filename = expected_url.rsplit("/", 1)[1]
    expected_line = f"{data['sha256']}  {filename}"
    if expected_line not in (pin / "sha256sums-signed-build.txt").read_text().splitlines():
        raise ValueError("The official published checksum differs from the pin")
    gpg = shutil.which("gpg")
    if not gpg:
        raise ValueError("Install gnupg to verify the pinned Tor Browser public key")
    key_fingerprint(pin / "tor-browser-developers.asc", gpg)
    return data


def verify_signature(archive: Path, pin: Path, data: dict) -> dict:
    if sha256(archive) != data["sha256"]:
        raise ValueError("Official Tor Browser bundle SHA-256 mismatch")
    gpg, gpgv = shutil.which("gpg"), shutil.which("gpgv")
    if not gpg or not gpgv:
        raise ValueError("Install gnupg and gpgv to verify the official Tor Browser signature")
    with tempfile.TemporaryDirectory(prefix="livara-tor-verify-") as temporary:
        ring = Path(temporary) / "trustedkeys.gpg"
        subprocess.run([gpg, "--no-options", "--homedir", temporary, "--batch", "--yes", "--output", str(ring),
                        "--dearmor", str(pin / "tor-browser-developers.asc")], check=True, capture_output=True)
        result = subprocess.run([gpgv, "--homedir", temporary, "--keyring", str(ring), "--status-fd", "1",
                                 str(pin / "bundle.sig.asc"), str(archive)], capture_output=True, text=True)
    signatures = [line.split()[2:] for line in result.stdout.splitlines() if line.startswith("[GNUPG:] VALIDSIG ")]
    if result.returncode or len(signatures) != 1:
        raise ValueError("The official detached Tor Browser signature could not be verified")
    signature = signatures[0]
    if len(signature) < 10 or signature[9] != PRIMARY or signature[7] not in ("8", "9", "10"):
        raise ValueError("Signature is not from the pinned Tor Browser primary/subkey chain using SHA-2")
    return {"primary_fingerprint": PRIMARY, "signing_fingerprint": signature[0], "signature_date": signature[1]}


def safe_member(member: tarfile.TarInfo) -> str:
    parts = PurePosixPath(member.name).parts
    if not parts or parts[0] != "tor-browser" or ".." in parts or member.name.startswith("/") or "\\" in member.name:
        raise ValueError("Unsafe path in the Tor Browser archive")
    relative = "/".join(parts[1:])
    if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
        raise ValueError("Unsupported special file in the Tor Browser archive")
    if member.issym() or member.islnk():
        target = posixpath.normpath(posixpath.join(posixpath.dirname(member.name), member.linkname) if member.issym() else member.linkname)
        if not target.startswith("tor-browser/") or member.linkname.startswith("/") or "\\" in member.linkname:
            raise ValueError("A Tor Browser archive link escapes its bundle")
    return relative


def verify_archive(archive: Path, pin: Path = PIN) -> dict:
    expected = json.loads((pin / "files.json").read_text())
    if expected.get("schema") != 1 or expected.get("archive_root") != "tor-browser":
        raise ValueError("Unsupported official file manifest")
    wanted = {entry["path"]: entry for entry in expected["entries"]}
    seen, expanded, elf = set(), 0, False
    with tarfile.open(archive, "r|xz") as bundle:
        for member in bundle:
            relative = safe_member(member)
            if not relative:
                continue
            if relative in seen or relative not in wanted or len(seen) >= 10000:
                raise ValueError("Unexpected or duplicate Tor Browser archive member")
            seen.add(relative)
            entry = wanted[relative]
            kind = "file" if member.isfile() else "directory" if member.isdir() else "symlink" if member.issym() else "hardlink"
            if entry["type"] != kind or member.mode != entry["mode"]:
                raise ValueError(f"Official file type or mode changed: {relative}")
            if member.isfile():
                expanded += member.size
                if expanded > 2 * 1024 * 1024 * 1024 or member.size != entry["size"]:
                    raise ValueError("Tor Browser expanded file size differs from its pin")
                digest, header = hashlib.sha256(), b""
                stream = bundle.extractfile(member)
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                    if not header:
                        header = block[:64]
                if digest.hexdigest() != entry["sha256"]:
                    raise ValueError(f"Official file contents changed: {relative}")
                if relative == "Browser/firefox.real":
                    elf = len(header) >= 20 and header[:6] == b"\x7fELF\x02\x01" and struct.unpack("<H", header[18:20])[0] == 62
            elif kind in ("symlink", "hardlink") and member.linkname != entry["target"]:
                raise ValueError("Official bundle link changed")
    if seen != set(wanted) or not elf or "Browser/start-tor-browser" not in seen:
        raise ValueError("The official Tor Browser bundle is incomplete or is not x86_64 ELF64")
    return {"members": len(seen), "expanded_bytes": expanded, "native_binary": "Browser/firefox.real", "elf_machine": "AMD64"}


def download(url: str, destination: Path) -> None:
    context = ssl.create_default_context()  # Honors the controller's configured CA trust.
    extra_ca = os.environ.get("LIVARA_BUILD_CA")
    if extra_ca:
        context.load_verify_locations(cafile=extra_ca)
    with urllib.request.urlopen(url, context=context, timeout=60) as response, destination.open("xb") as stream:
        final = urllib.parse.urlsplit(response.url)
        if final.scheme != "https" or not (final.hostname or "").endswith(".torproject.org"):
            raise ValueError("The official bundle download redirected outside Tor Project HTTPS")
        size = 0
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > MAX_DOWNLOAD:
                raise ValueError("Tor Browser download exceeded the bounded artifact size")
            stream.write(block)


def prepare(output: Path, local_archive: Path | None = None, pin: Path = PIN) -> Path:
    data = check_pin(pin)
    output.mkdir(parents=True, exist_ok=True)
    target = output / ARTIFACT
    with tempfile.TemporaryDirectory(prefix=".tor-prepare-", dir=output) as temporary:
        staged = Path(temporary) / ARTIFACT
        if local_archive is not None:
            try:
                os.link(local_archive, staged)
            except OSError:
                shutil.copyfile(local_archive, staged)
        elif target.is_file() and sha256(target) == data["sha256"]:
            os.link(target, staged)
        else:
            download(data["archive_url"], staged)
        signature = verify_signature(staged, pin, data)
        contents = verify_archive(staged, pin)
        os.replace(staged, target)
    report = {"schema": 1, "version": data["version"], "archive_sha256": data["sha256"],
              "archive_bytes": target.stat().st_size, "unchanged_official_archive": True,
              "signature": signature, "contents": contents}
    (output / "livara-tor-browser-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Official Tor Browser {data['version']}: signature, SHA-256, {contents['members']} original members and ELF64 verified")
    print(target)
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path)
    parser.add_argument("--check", action="store_true", help="Validate only local pins/key; never download")
    parser.add_argument("--archive", type=Path, help="Verify an existing official archive instead of downloading")
    args = parser.parse_args(argv)
    try:
        if args.check:
            pin = check_pin()
            print(f"Official Tor Browser {pin['version']}: offline pin and primary signing-key check passed")
            return 0
        if args.output is None:
            parser.error("output directory is required without --check")
        prepare(args.output, args.archive)
        return 0
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Tor Browser preparation failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
