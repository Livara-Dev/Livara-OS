from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from livara import gpu


class GraphicsObservations(unittest.TestCase):
    def test_rtx_generations_and_unclassified_models(self):
        for model, expected in (("NVIDIA GeForce RTX 2080 Ti", "Turing / RTX 20"), ("GeForce RTX 3060 Laptop GPU", "Ampere / RTX 30"), ("NVIDIA GeForce RTX 4090", "Ada / RTX 40"), ("NVIDIA GeForce RTX 5090", "Blackwell / RTX 50")):
            self.assertEqual(gpu.generation(model), expected)
        for model in ("RTX A2000", "Quadro RTX 5000", "GeForce GTX 1080", "RTX 50000"):
            self.assertIsNone(gpu.generation(model))

    def test_pci_display_filter_and_driver_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            driver = root / "drivers" / "nvidia"
            driver.mkdir(parents=True)
            for slot, vendor, class_id in (("0000:01:00.0", "0x10de", "0x030000"), ("0000:01:00.1", "0x10de", "0x040300"), ("0000:02:00.0", "0x8086", "0x030000")):
                device = root / slot
                device.mkdir()
                (device / "vendor").write_text(vendor)
                (device / "class").write_text(class_id)
                (device / "device").write_text("0x2b85")
            (root / "0000:01:00.0" / "driver").symlink_to(driver, target_is_directory=True)
            self.assertEqual(gpu.pci_devices(root), [{"slot": "0000:01:00.0", "device_id": "0x2b85", "driver": "nvidia"}])

    def test_csv_parsing_and_no_invented_gpu_readings(self):
        text = "NVIDIA GeForce RTX 5090, 580.178.04, 00000000:01:00.0, 32768, 39\ninvalid, unknown, bad, 0, 0\npartial\n"
        result = gpu.parse_smi(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["memory_mib"], "32768")
        self.assertEqual(result[0]["generation"], "Blackwell / RTX 50")
        self.assertIn("No NVIDIA", gpu.assess([], []))
        self.assertIn("not verified", gpu.assess([{"slot": "01:00.0"}], []))
        self.assertIn("too old", gpu.assess([], [{**result[0], "driver": "550.120"}], "Open Kernel Module"))
        self.assertIn("not been verified", gpu.assess([], result, "NVIDIA UNIX x86_64 Kernel Module"))
        self.assertIn("still require hardware testing", gpu.assess([], result, "NVIDIA UNIX Open Kernel Module for x86_64"))

    def test_cpu_core_ultra_model_and_actual_topology_frequency_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cpuinfo = root / "cpuinfo"
            block = "processor : {logical}\nvendor_id : GenuineIntel\nmodel name : Intel(R) Core(TM) Ultra 7 155H\ncpu family : 6\nmodel : 170\nstepping : 4\nmicrocode : 0x26\nphysical id : 0\ncore id : {core}\nflags : hwp hwp_epp sse2 avx2\n"
            cpuinfo.write_text("\n".join(block.format(logical=index, core=index // 2) for index in range(4)))
            cpu_root = root / "sys"
            (cpu_root / "intel_pstate").mkdir(parents=True)
            (cpu_root / "intel_pstate" / "status").write_text("active")
            policy = cpu_root / "cpufreq" / "policy0"
            policy.mkdir(parents=True)
            (policy / "scaling_driver").write_text("intel_pstate")
            (policy / "scaling_governor").write_text("powersave")
            (policy / "energy_performance_preference").write_text("balance_power")
            report = gpu.cpu_observation(cpuinfo, cpu_root)
            self.assertEqual(report["model"], "Intel(R) Core(TM) Ultra 7 155H")
            self.assertTrue(report["core_ultra_7"])
            self.assertEqual(report["logical_processors_observed"], 4)
            self.assertEqual(report["physical_cores_observed"], 2)
            self.assertEqual(report["intel_pstate"], "active")
            self.assertTrue(report["hwp_advertised"])
            self.assertEqual(report["frequency_policies"][0]["energy_preference"], "balance_power")
            self.assertNotIn("performance_cores", report)
            self.assertNotIn("efficiency_cores", report)
            self.assertEqual((policy / "scaling_governor").read_text(), "powersave")

    def test_unknown_topology_does_not_infer_hybrid_counts_or_ultra_sku(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cpuinfo").write_text("processor : 0\nmodel name : Intel(R) Core(TM) Ultra 7 258V\nvendor_id : GenuineIntel\nflags : sse2\n")
            report = gpu.cpu_observation(root / "cpuinfo", root / "missing-sys")
            self.assertTrue(report["core_ultra_7"])
            self.assertIsNone(report["physical_cores_observed"])
            self.assertEqual(report["frequency_policies"], [])
            self.assertEqual(report["intel_pstate"], "Unavailable")
            self.assertFalse(report["hwp_advertised"])
            self.assertNotIn("architecture_generation", report)
            (root / "cpuinfo").write_text("processor : 0\nmodel name : Intel(R) Core(TM) i7-13700H\n")
            self.assertFalse(gpu.cpu_observation(root / "cpuinfo", root)["core_ultra_7"])

    def test_intel_xe_and_i915_are_reported_without_requiring_nvidia(self):
        for driver_name in ("i915", "xe"):
            with self.subTest(driver=driver_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                driver = root / "drivers" / driver_name
                driver.mkdir(parents=True)
                device = root / "0000:00:02.0"
                device.mkdir()
                (device / "vendor").write_text("0x8086")
                (device / "class").write_text("0x030000")
                (device / "device").write_text("0x7d55")
                (device / "driver").symlink_to(driver, target_is_directory=True)
                intel = gpu.pci_devices(root, vendor="0x8086")
                self.assertEqual(intel[0]["driver"], driver_name)
                self.assertEqual(gpu.pci_devices(root), [])
                summary = gpu.combined_assessment([], [], "", intel)
                self.assertIn("Intel graphics detected", summary)
                self.assertIn("NVIDIA drivers are not needed", summary)
                self.assertNotIn("No Intel", summary)
                hybrid = gpu.combined_assessment([{"slot": "01:00.0"}], [], "", intel)
                self.assertIn("both detected", hybrid)
                self.assertIn("not verified", hybrid)

    def test_install_plan_is_explicit_fixed_and_not_executed(self):
        with patch("livara.gpu.subprocess.run") as run:
            command = gpu.installation_command()
            self.assertEqual(command[0], "livara-terminal")
            self.assertEqual(command[-4:], list(gpu.DRIVER_PACKAGES))
            self.assertIn('install "$@"', command[4])
            self.assertNotIn("-y", command[4])
            run.assert_not_called()

    def test_no_hardware_report_does_not_run_install_or_nvidia_settings(self):
        calls = []
        def observe(arguments, **kwargs):
            calls.append(arguments)
            return 127, "Not installed"
        with patch("livara.gpu.pci_devices", return_value=[]), patch("livara.gpu.run_readonly", side_effect=observe):
            report = gpu.diagnostics()
        self.assertEqual(report["gpus"], [])
        self.assertIn("No Intel or NVIDIA", report["assessment"])
        self.assertEqual({call[0] for call in calls}, {"nvidia-smi", "lspci", "mokutil", "prime-select", "powerprofilesctl"})
        self.assertEqual(report["recommended_packages"], list(gpu.DRIVER_PACKAGES))


if __name__ == "__main__":
    unittest.main()
