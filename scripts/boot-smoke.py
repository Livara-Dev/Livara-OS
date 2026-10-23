#!/usr/bin/env python3
"""Boot the actual ISO under QEMU, select its serial test entry, and retain proof.

Run in the assembler image, with the project at /project. Uses TCG, not KVM,
and does not attach any host disks. BIOS and UEFI are separate invocations.
"""

import argparse
import json
import re
import select
import socket
import subprocess
import time
from pathlib import Path


def connect(path, process, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"QEMU exited with status {process.returncode}")
        connection = socket.socket(socket.AF_UNIX)
        try:
            connection.connect(str(path))
            return connection
        except (FileNotFoundError, ConnectionRefusedError):
            connection.close()
            time.sleep(0.1)
    raise TimeoutError(f"QEMU socket did not start: {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path("/project"))
    parser.add_argument("--firmware", choices=("bios", "uefi"), default="bios")
    parser.add_argument("--safe-graphics", action="store_true", help="Use the image's nomodeset compatibility boot parameters")
    parser.add_argument("--desktop-only", action="store_true", help="Stop after native checks and a settled desktop; do not wait for a second Kali import")
    parser.add_argument("--capture-menus", action="store_true", help="Also capture the real GNOME quick-settings menu for visual review")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if args.safe_graphics and not args.desktop_only:
        parser.error("--safe-graphics requires --desktop-only; compatibility mode is a visual boot check")
    project = args.project.resolve()
    output = project / ".build" / (f"boot-{args.firmware}" + ("-safe" if args.safe_graphics else ""))
    output.mkdir(parents=True, exist_ok=True)
    serial_path = output / "serial.sock"
    qmp_path = output / "qmp.sock"
    for path in (serial_path, qmp_path):
        path.unlink(missing_ok=True)
    command = ["qemu-system-x86_64", "-m", "4096", "-smp", "2", "-cpu", "qemu64", "-accel", "tcg,thread=multi",
               "-cdrom", str(project / "dist/livara-os-0.1.0-amd64.iso"), "-boot", "d",
               "-vga", "virtio", "-display", "none", "-no-reboot",
               "-nic", "user,model=virtio-net-pci", "-qmp", f"unix:{qmp_path},server=on,wait=off",
               "-serial", f"unix:{serial_path},server=on,wait=on"]
    if args.firmware == "uefi":
        command += ["-bios", "/usr/share/ovmf/OVMF.fd"]
    stderr_file = (output / "qemu.log").open("wb")
    process = subprocess.Popen(command, stdout=stderr_file, stderr=stderr_file)
    serial = None
    qmp = None
    passed = False
    try:
        serial = connect(serial_path, process)
        qmp = connect(qmp_path, process)
        qmp_stream = qmp.makefile("rwb", buffering=0)
        qmp_stream.readline()
        qmp_stream.write(b'{"execute":"qmp_capabilities"}\n')
        while "return" not in json.loads(qmp_stream.readline()):
            pass
        transcript = bytearray()
        selected = False
        desktop_seen_at = None
        failure_seen_at = None
        deadline = time.monotonic() + args.timeout
        next_report = time.monotonic() + 15
        next_screenshot = time.monotonic() + 60
        started = time.monotonic()
        print(f"Booting {args.firmware.upper()} ISO under QEMU TCG", flush=True)
        with (output / "serial.log").open("wb") as log:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                if select.select([serial], [], [], 1)[0]:
                    chunk = serial.recv(65536)
                    if not chunk:
                        break
                    transcript.extend(chunk)
                    log.write(chunk)
                    log.flush()
                    if not selected and b"Try Livara OS" in transcript:
                        if args.safe_graphics:
                            # Boot the compatibility entry itself; its quiet kernel line
                            # does not run the serial self-test. Review the captured UI.
                            time.sleep(1)
                            serial.sendall(b"s")
                        else:
                            # GRUB's terminal receives standard ANSI down-arrow sequences.
                            time.sleep(1)
                            serial.sendall(b"d")
                        selected = True
                        print("Selected compatibility graphics" if args.safe_graphics else "Selected the integration-test GRUB entry", flush=True)
                    if b"LIVARA_SELFTEST_PASS" in transcript:
                        passed = True
                        break
                    if b"LIVARA_SELFTEST_FAIL" in transcript and failure_seen_at is None:
                        failure_seen_at = time.monotonic()
                    if b"LIVARA_SELFTEST_LOG_END" in transcript or b"Kernel panic" in transcript:
                        break
                    if args.desktop_only and desktop_seen_at is None and b"LIVARA_CENTER_OK" in transcript:
                        desktop_seen_at = time.monotonic()
                if desktop_seen_at is not None and time.monotonic() - desktop_seen_at >= 120:
                    passed = True
                    break
                if failure_seen_at is not None and time.monotonic() - failure_seen_at >= 30:
                    break
                if args.safe_graphics and time.monotonic() - started >= 300:
                    break
                if time.monotonic() >= next_report:
                    clean = re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", bytes(transcript[-1800:]))
                    last = clean.decode(errors="replace").splitlines()[-1:]
                    print(f"{int(time.monotonic() - started)}s: {' '.join(last)[-180:]}", flush=True)
                    next_report = time.monotonic() + 15
                if time.monotonic() >= next_screenshot:
                    qmp_stream.write((json.dumps({"execute": "screendump", "arguments": {"filename": str(output / "progress.ppm")}}) + "\n").encode())
                    while True:
                        reply = json.loads(qmp_stream.readline())
                        if "return" in reply or "error" in reply:
                            break
                    if (output / "progress.ppm").exists():
                        from PIL import Image
                        Image.open(output / "progress.ppm").save(output / "progress.png")
                    next_screenshot = time.monotonic() + 60
        # Allow a pending desktop frame to finish before capturing it.
        time.sleep(2)
        ppm = output / "desktop.ppm"
        qmp_stream.write((json.dumps({"execute": "screendump", "arguments": {"filename": str(ppm)}}) + "\n").encode())
        while True:
            reply = json.loads(qmp_stream.readline())
            if "return" in reply or "error" in reply:
                break
        if ppm.exists():
            from PIL import Image
            Image.open(ppm).save(output / "desktop.png")
        if passed and args.capture_menus:
            qmp_stream.write((json.dumps({"execute": "human-monitor-command", "arguments": {"command-line": "sendkey meta_l-s"}}) + "\n").encode())
            while True:
                reply = json.loads(qmp_stream.readline())
                if "return" in reply or "error" in reply:
                    break
            time.sleep(8)
            menu_ppm = output / "quick-settings.ppm"
            qmp_stream.write((json.dumps({"execute": "screendump", "arguments": {"filename": str(menu_ppm)}}) + "\n").encode())
            while True:
                reply = json.loads(qmp_stream.readline())
                if "return" in reply or "error" in reply:
                    break
            if menu_ppm.exists():
                Image.open(menu_ppm).save(output / "quick-settings.png")
        (output / "result.json").write_text(json.dumps({"firmware": args.firmware, "safe_graphics": args.safe_graphics, "desktop_only": args.desktop_only, "passed": None if args.safe_graphics else passed, "seconds": round(time.monotonic() - started), "grub_entry_selected": selected}, indent=2) + "\n")
        print("CAPTURED — manually review the compatibility desktop screenshot" if args.safe_graphics else "PASS" if passed else "FAIL — inspect the retained serial log and screenshot", flush=True)
    finally:
        if serial:
            serial.close()
        if qmp:
            qmp.close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        stderr_file.close()
    return 0 if passed or args.safe_graphics else 1


if __name__ == "__main__":
    raise SystemExit(main())

