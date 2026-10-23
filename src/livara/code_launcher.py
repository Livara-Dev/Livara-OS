"""Launch the separately compiled, 64-bit Livara Code application."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BINARY = Path('/opt/livara-code/bin/livara-code')


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not BINARY.is_file() or not os.access(BINARY, os.X_OK):
        print('Livara Code is not installed. Build the Livara application sources with Build-Livara.bat, or scripts/build-code.sh on Linux. See docs/code-editor.md.', file=sys.stderr)
        return 127
    try:
        os.execv(str(BINARY), [str(BINARY), *arguments])
    except OSError as error:
        print(f'Livara Code could not start: {error}', file=sys.stderr)
        return 126
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
