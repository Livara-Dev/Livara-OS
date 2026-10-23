"""Source-build and launcher checks; no upstream binary is substituted."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FORK = ROOT / "forks/browser"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = load("livara_browser_runtime", ROOT / "share/livara/browser/runtime.py")
prepare = load("livara_browser_prepare", FORK / "prepare.py")
packager = load("livara_browser_packager", FORK / "package-build.py")


class BrowserFork(unittest.TestCase):
    def test_pinned_upstream_engine_and_toolchain(self):
        manifest = json.loads((FORK / "upstream.json").read_text())
        self.assertRegex(manifest["commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(manifest["firefox"]["sha512"], r"^[0-9a-f]{128}$")
        self.assertIn(manifest["firefox"]["version"], manifest["firefox"]["source_url"])
        self.assertEqual(manifest["license"], "MPL-2.0")
        self.assertIn("Mozilla Public License", (FORK / "LICENSE-MPL-2.0").read_text())

    @unittest.skipUnless((ROOT / ".build/upstreams/zen/.git").is_dir(), "local pinned source checkout not present")
    def test_patch_applies_to_actual_pinned_zen_source(self):
        result = prepare.validate(ROOT / ".build/upstreams/zen")
        self.assertEqual(result["tag"], "1.23.4b")

    def test_onions_require_explicit_tor_not_search_terms(self):
        for address in ("example.onion", "http://example.onion/a", "https://EXAMPLE.ONION./"):
            with self.subTest(address=address), self.assertRaisesRegex(ValueError, "explicit Tor"):
                runtime.normalize_urls([address])
        self.assertEqual(runtime.normalize_urls(["example.onion"], tor=True), ["http://example.onion"])
        self.assertIn("duckduckgo.com/?q=", runtime.normalize_urls(["what is an .onion address"])[0])
        for address in ("file:///etc/passwd", "javascript:alert(1)", "https://user:secret@example.com"):
            with self.assertRaises(ValueError):
                runtime.normalize_urls([address])

    def test_normal_launch_strips_inherited_tor_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "livara-browser"
            binary.write_text("fixture")
            binary.chmod(0o755)
            with patch.object(runtime, "NATIVE_BINARY", binary), patch.dict(os.environ, {"LIVARA_TOR_MODE": "1", "LIVARA_TOR_SOCKS_PORT": "9999"}), patch.object(runtime.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)) as run:
                self.assertEqual(runtime.main(["example.com"]), 0)
                arguments, keywords = run.call_args
                self.assertEqual(arguments[0], [str(binary), "https://example.com"])
                self.assertNotIn("LIVARA_TOR_MODE", keywords["env"])
                self.assertNotIn("LIVARA_TOR_SOCKS_PORT", keywords["env"])

    def test_missing_native_fork_never_falls_back(self):
        with patch.object(runtime, "NATIVE_BINARY", Path("/missing/livara/browser")), patch.object(runtime.subprocess, "run") as run, contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(runtime.main([]), 1)
            run.assert_not_called()
            self.assertIn("No stock-browser or WebKit fallback", error.getvalue())

    def test_tor_dispatch_is_explicit_and_separate(self):
        calls = []
        module = types.SimpleNamespace(run_tor_browser=lambda urls: calls.append(urls) or 0)
        with patch.object(runtime, "NATIVE_BINARY", Path("/missing/normal/browser")), patch.dict(sys.modules, {"official_tor": module}), patch.object(runtime.subprocess, "run") as run:
            self.assertEqual(runtime.main(["--tor", "example.onion"]), 0)
            self.assertEqual(calls, [["http://example.onion"]])
            run.assert_not_called()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(runtime.main(["--tor", "--private-window", "example.onion"]), 1)
            self.assertEqual(len(calls), 1)

    def test_packager_rejects_script_instead_of_compiled_browser(self):
        with tempfile.TemporaryDirectory() as temporary:
            dist = Path(temporary) / "dist"
            app = dist / "livara-browser"
            app.mkdir(parents=True)
            binary = app / "livara-browser"
            binary.write_text("#!/bin/sh\nexec zen\n"); binary.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "compiled Linux ELF"):
                packager.package(dist, Path(temporary) / "out")

    def test_locale_branding_preserves_ids_comments_and_legal_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "locales/en-US").mkdir(parents=True)
            ftl = root / "locales/en-US/test.ftl"
            ftl.write_text("# Zen contributor attribution\nzen-title = Zen Browser Settings\n    .label = Zen Mods\nzen-code = ZenUIManager\n")
            legal = root / "LICENSE"
            legal.write_text("Zen copyright")
            prepare.rebrand_locales(root)
            self.assertIn("zen-title = Livara Browser Settings", ftl.read_text())
            self.assertIn("# Zen contributor attribution", ftl.read_text())
            self.assertIn("ZenUIManager", ftl.read_text())
            self.assertEqual(legal.read_text(), "Zen copyright")

    @unittest.skipUnless(shutil.which("node"), "Node required to execute autoconfig policy checks")
    def test_normal_autoconfig_cannot_enable_legacy_proxy_mode(self):
        policy = FORK / "runtime/livara.cfg"
        code = r'''const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(process.argv[1],'utf8');
function apply(env){const prefs={};vm.runInNewContext(source,{getenv:k=>env[k]||'',lockPref:(k,v)=>prefs[k]=v});return prefs;}
const normal=apply({});if(normal['network.dns.blockDotOnion']!==true)throw Error('normal onions');
const inherited=apply({LIVARA_TOR_MODE:'1',LIVARA_TOR_SOCKS_PORT:'19050'});
if(JSON.stringify(inherited)!==JSON.stringify(normal)||Object.keys(inherited).length!==1)throw Error('legacy Tor mode changed normal browser network policy');
'''
        subprocess.run(["node", "-e", code, str(policy)], check=True, capture_output=True, text=True)
