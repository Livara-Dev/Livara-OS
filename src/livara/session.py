"""Refresh generated per-user appearance at login without resetting preferences.

System schema overrides only select the button layout. GTK's colored controls
are per-user CSS and must also be installed for upgraded and installed accounts,
not only the ephemeral ISO live session.
"""
from __future__ import annotations

import sys

from . import desktop


def refresh(*, config_home=None):
    if desktop.settings_for("org.livara.desktop") is None:
        raise ValueError("Livara desktop schemas are unavailable; no user styles were changed")
    return desktop.apply_window_style(config_home=config_home)


def main():
    try:
        changed = refresh()
    except (OSError, ValueError) as error:
        print(f"Livara session appearance: {error}", file=sys.stderr)
        return 1
    print(f"Livara session appearance: {len(changed)} stylesheet(s) refreshed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
