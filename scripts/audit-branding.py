#!/usr/bin/env python3
"""Audit known Ubuntu identity graphics without changing the image."""
import importlib.util
from pathlib import Path
import sys

source = Path(__file__).resolve().parents[1] / "share/livara/branding/apply-branding.py"
spec = importlib.util.spec_from_file_location("livara_branding", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if "--audit" not in sys.argv:
    sys.argv.append("--audit")
raise SystemExit(module.main())
