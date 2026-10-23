"""Launch the source-built Livara Browser with an explicit optional Tor mode."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

from livara.web import normalize_address

NATIVE_BINARY = Path("/opt/livara-browser/livara-browser")


def is_onion(uri: str) -> bool:
    hostname = (urlsplit(uri).hostname or "").lower().rstrip(".")
    return hostname.endswith(".onion")


def normalize_urls(values: list[str], tor: bool = False) -> list[str]:
    urls = []
    for value in values:
        if tor and "://" not in value and ".onion" in value.split("/", 1)[0].lower():
            value = "http://" + value
        uri = normalize_address(value)
        if is_onion(uri) and not tor:
            raise ValueError("Onion websites require an explicit Tor session. Use Livara Browser's Tor Mode action or: livara-browser --tor ADDRESS")
        urls.append(uri)
    return urls


def normal_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("LIVARA_TOR_SOCKS_PORT", None)
    environment.pop("LIVARA_TOR_MODE", None)
    return environment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Livara Browser — browse the web or open official Tor Browser")
    parser.add_argument("--tor", action="store_true", help="open the separately verified official Tor Browser with its original security configuration")
    parser.add_argument("--private-window", action="store_true")
    parser.add_argument("--new-window", action="store_true")
    parser.add_argument("--new-tab", action="store_true")
    parser.add_argument("--kiosk", action="store_true")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--offline", action="store_true", help="start the compiled browser in offline mode")
    parser.add_argument("--version", action="store_true", help="show the compiled browser version")
    parser.add_argument("addresses", nargs="*")
    args = parser.parse_args(argv)
    if args.tor and (args.offline or args.version):
        parser.error("--tor cannot be combined with --offline or --version")
    try:
        urls = normalize_urls(args.addresses, args.tor)
        flags = ["--" + name.replace("_", "-") for name in
                 ("private_window", "new_window", "new_tab", "kiosk", "fullscreen", "offline", "version")
                 if getattr(args, name)]
        if args.tor:
            if flags:
                raise ValueError("Tor Browser uses its official window and privacy controls; --tor accepts website addresses only")
            from official_tor import run_tor_browser
            return run_tor_browser(urls)
        if not NATIVE_BINARY.is_file() or not os.access(NATIVE_BINARY, os.X_OK):
            raise RuntimeError("The source-built Livara Browser is missing. Run scripts/build-browser.sh and include its artifact when building Livara OS. No stock-browser or WebKit fallback is used.")
        return subprocess.run([str(NATIVE_BINARY), *flags, *urls], env=normal_environment()).returncode
    except (ValueError, RuntimeError, OSError) as error:
        print(f"Livara Browser: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
