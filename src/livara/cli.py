"""The `livara` command line interface."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import sys
from pathlib import Path

from . import __version__, core


def emit(value: object) -> None:
    print(json.dumps(value, indent=2))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="livara", description="Livara OS · your desktop, your workbench")
    root.add_argument("--version", action="version", version=f"Livara {__version__}")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("center", help="Open the native Livara Control Center")
    status = commands.add_parser("status", aliases=["doctor"], help="Read real system health and tool availability")
    status.add_argument("--json", action="store_true")
    shield = commands.add_parser("shield", help="Read-only checks of local security settings")
    shield.add_argument("--json", action="store_true")
    verify = commands.add_parser("verify", help="Calculate or verify a file's SHA-256")
    verify.add_argument("file", type=Path)
    verify.add_argument("--sha256", metavar="EXPECTED")
    cases = commands.add_parser("case", help="Create and verify a local evidence workspace")
    case_commands = cases.add_subparsers(dest="action", required=True)
    new = case_commands.add_parser("new", help="Create a private workspace")
    new.add_argument("name")
    new.add_argument("--directory", type=Path)
    for action in ("seal", "verify"):
        item = case_commands.add_parser(action)
        item.add_argument("directory", type=Path)
    toolbox = commands.add_parser("toolbox", help="Manage the isolated, rootless Kali toolbox")
    tool_commands = toolbox.add_subparsers(dest="action", required=True)
    listing = tool_commands.add_parser("list")
    listing.add_argument("--json", action="store_true")
    storage = tool_commands.add_parser("storage", help="Choose persistent storage for Kali images; existing images are not moved")
    storage.add_argument("directory", type=Path, nargs="?")
    setup = tool_commands.add_parser("setup", help="Load the bundled core or build a Kali profile")
    setup.add_argument("--profile", choices=core.PROFILES, default="core")
    setup.add_argument("--refresh", action="store_true", help="Build from current upstream instead of the bundled archive")
    setup.add_argument("--dry-run", action="store_true")
    run = tool_commands.add_parser("run", help="Run a command inside Kali; arguments follow --")
    run.add_argument("--profile", choices=core.PROFILES, default="core")
    run.add_argument("--directory", type=Path)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("tool_command", nargs=argparse.REMAINDER)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "center":
            from .gui import main as gui_main
            return gui_main()
        if args.command in ("status", "doctor"):
            status = core.system_status()
            if args.json:
                emit(status)
            else:
                print(f"Livara {__version__} · {status['distribution']}")
                print(f"Kernel      {status['kernel']} ({status['architecture']})")
                print(f"Memory      {status['memory_available'] / 2**30:.1f} / {status['memory_total'] / 2**30:.1f} GiB available")
                print(f"Storage     {status['disk_free'] / 2**30:.1f} GiB free")
                print(f"Native tools {status['native_tools_installed']} installed · Kali runtime {'available' if status['podman_available'] else 'not installed'}")
                for interface in status["interfaces"]:
                    print(f"Network     {interface['name']} · {interface['state']}")
        elif args.command == "shield":
            report = core.shield_report()
            if args.json:
                emit(report)
            else:
                for item in report:
                    print(f"{item['state'].upper():7} {item['name']}: {item['detail']}")
        elif args.command == "verify":
            digest, valid = core.verify_file(args.file, args.sha256)
            print(f"{digest}  {args.file}")
            if args.sha256:
                print("SHA-256 matches" if valid else "SHA-256 MISMATCH", file=sys.stdout if valid else sys.stderr)
            return 0 if valid else 1
        elif args.command == "case":
            if args.action == "new":
                print(core.create_case(args.name, args.directory))
            elif args.action == "seal":
                manifest = core.seal_case(args.directory)
                print(f"Sealed {len(manifest['files'])} files. Keep a trusted copy of manifest.json separately.")
            else:
                report = core.verify_case(args.directory)
                emit(report)
                return 0 if report["ok"] else 1
        elif args.command == "toolbox":
            if args.action == "storage":
                print(core.configure_toolbox_storage(args.directory) if args.directory else core.toolbox_storage() or "Default Podman user storage")
            elif args.action == "list":
                if args.json:
                    emit({"profiles": core.PROFILES, "tools": [{**tool, "host_installed": bool(tool["command"] and shutil.which(tool["command"]))} for tool in core.TOOLS]})
                else:
                    for name, description in core.PROFILES.items():
                        print(f"{name:12} {description}")
                    print("\nPrepare: livara toolbox setup\nEnter:   livara toolbox run -- bash")
            else:
                if args.action == "setup":
                    command = core.toolbox_setup_command(args.profile, args.refresh)
                else:
                    tool_command = args.tool_command
                    if tool_command[:1] == ["--"]:
                        tool_command = tool_command[1:]
                    command = core.toolbox_run_command(args.profile, tool_command, args.directory)
                if args.dry_run:
                    print(shlex.join(command))
                else:
                    return core.execute(command)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"livara: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

