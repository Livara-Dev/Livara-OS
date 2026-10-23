import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from livara import monitor


def stat_text(pid=800, name="worker (with) parentheses", started=12345, ticks=80):
    fields = ["0"] * 40
    fields[0] = "S"
    fields[1] = "20"
    fields[11] = str(ticks)
    fields[12] = "15"
    fields[17] = "3"
    fields[19] = str(started)
    fields[20] = "8192"
    fields[21] = "12"
    return f"{pid} ({name}) " + " ".join(fields)


class ResourceParsing(unittest.TestCase):
    def test_cpu_does_not_double_count_guest_ticks_and_handles_reset(self):
        current = monitor.parse_cpu("cpu  100 20 30 400 10 5 6 7 50 20\ncpu0 1 2 3 4\n")
        self.assertEqual(current, (578, 410))
        self.assertEqual(monitor.cpu_usage((100, 50), (200, 75)), 75)
        self.assertEqual(monitor.cpu_usage((200, 75), (100, 50)), 0)
        self.assertEqual(monitor.cpu_usage(None, current), 0)

    def test_memory_uses_available_and_counts_swap(self):
        values = monitor.parse_memory("MemTotal: 1000 kB\nMemAvailable: 400 kB\nSwapTotal: 500 kB\nSwapFree: 200 kB\n")
        self.assertEqual(values["memory_used"], 600 * 1024)
        self.assertEqual(values["swap_used"], 300 * 1024)
        fallback = monitor.parse_memory("MemTotal: 1000 kB\nMemFree: 200 kB\nBuffers: 30 kB\nCached: 80 kB\n")
        self.assertEqual(fallback["memory_available"], 310 * 1024)

    def test_network_handles_hotplug_counter_reset_and_loopback(self):
        text = "Inter-| Receive\n lo: 999 0 0 0 0 0 0 0 999 0\n eth0: 1000 0 0 0 0 0 0 0 2000 0\n"
        self.assertEqual(monitor.parse_network(text), {"eth0": (1000, 2000)})
        self.assertEqual(monitor.network_rates({"eth0": (100, 200)}, {"eth0": (300, 260), "new": (9000, 9000)}, 2), (100, 30))
        self.assertEqual(monitor.network_rates({"eth0": (900, 800)}, {"eth0": (20, 10)}, 1), (0, 0))

    def test_process_names_with_parentheses_keep_field_positions(self):
        fields = monitor.parse_process_stat(stat_text())
        self.assertEqual(fields["name"], "worker (with) parentheses")
        self.assertEqual(fields["started"], 12345)
        self.assertEqual(fields["ticks"], 95)
        self.assertEqual(fields["threads"], 3)
        self.assertEqual(fields["rss"], 12 * os.sysconf("SC_PAGE_SIZE"))

    def test_process_observation_handles_non_utf8_names_and_command_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "800"
            folder.mkdir()
            (folder / "stat").write_bytes(stat_text(name="worker").encode().replace(b"worker", b"work\xffr"))
            (folder / "status").write_text("Uid:\t1000\t1001\t1001\t1001\n")
            (folder / "cmdline").write_bytes(b"worker\x00literal; $(command)\x00")
            process = monitor.read_process(800, Path(directory))
            self.assertEqual(process.uid, 1001)
            self.assertEqual(process.command, "worker literal; $(command)")
            self.assertIn("\ufffd", process.name)

    def test_real_sampler_observes_this_process_and_disk(self):
        sampler = monitor.Sampler()
        first = sampler.sample()
        second = sampler.sample()
        self.assertGreater(first.memory_total, 0)
        self.assertGreater(first.disk_total, 0)
        self.assertGreater(first.uptime, 0)
        self.assertTrue(any(process.pid == os.getpid() for process in first.processes))
        self.assertTrue(0 <= second.cpu <= 100)
        self.assertGreaterEqual(second.network_receive, 0)

    def test_report_is_private_and_does_not_replace_existing_file(self):
        sample = monitor.Sampler().sample()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            monitor.export_snapshot(sample, path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text())["schema"], 1)
            with self.assertRaises(FileExistsError):
                monitor.export_snapshot(sample, path)


class ProcessControl(unittest.TestCase):
    def setUp(self):
        self.selected = monitor.Process(808080, "owned worker", "S", 1, os.geteuid(), 123, 10, 4096, 1, "worker")

    def test_reused_pid_is_refused_before_opening_a_pidfd(self):
        with patch.object(monitor, "read_process", return_value=replace(self.selected, started=124)), patch.object(os, "pidfd_open") as opened, patch.object(signal, "pidfd_send_signal") as sent:
            with self.assertRaises(ProcessLookupError):
                monitor.control_process(self.selected, "terminate")
            opened.assert_not_called()
            sent.assert_not_called()

    def test_reuse_between_check_and_open_is_refused_and_descriptor_closed(self):
        with patch.object(monitor, "read_process", side_effect=[self.selected, replace(self.selected, started=124)]), patch.object(os, "pidfd_open", return_value=1001), patch.object(os, "close") as close, patch.object(signal, "pidfd_send_signal") as sent:
            with self.assertRaises(ProcessLookupError):
                monitor.control_process(self.selected, "pause")
            sent.assert_not_called()
            close.assert_called_once_with(1001)

    def test_signal_uses_pinned_descriptor_instead_of_naked_pid(self):
        with patch.object(monitor, "read_process", return_value=self.selected), patch.object(os, "pidfd_open", return_value=1001) as opened, patch.object(os, "close") as close, patch.object(signal, "pidfd_send_signal") as sent:
            monitor.control_process(self.selected, "resume")
            opened.assert_called_once_with(self.selected.pid, 0)
            sent.assert_called_once_with(1001, signal.SIGCONT, None, 0)
            close.assert_called_once_with(1001)

    def test_other_users_and_protected_processes_are_refused(self):
        with patch.object(os, "pidfd_open") as opened:
            for process in (replace(self.selected, uid=os.geteuid() + 1), replace(self.selected, pid=1), replace(self.selected, pid=os.getpid())):
                with self.subTest(pid=process.pid, uid=process.uid), self.assertRaises(PermissionError):
                    monitor.control_process(process, "terminate")
            opened.assert_not_called()

    def test_permission_or_exit_errors_still_close_pinned_descriptor(self):
        with patch.object(monitor, "read_process", return_value=self.selected), patch.object(os, "pidfd_open", return_value=1001), patch.object(os, "close") as close, patch.object(signal, "pidfd_send_signal", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                monitor.control_process(self.selected, "terminate")
            close.assert_called_once_with(1001)

    @unittest.skipUnless(hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"), "Linux pidfd support required")
    def test_real_signal_is_limited_to_a_controlled_child(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            selected = monitor.read_process(process.pid)
            monitor.control_process(selected, "terminate")
            self.assertEqual(process.wait(timeout=5), -signal.SIGTERM)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
