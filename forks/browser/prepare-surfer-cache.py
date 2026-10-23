#!/usr/bin/env python3
"""Make the pinned Surfer downloader use Livara's verified local source archive.
The caller verifies SHA-512 before invoking Surfer. Without this patch Surfer
unconditionally downloads the same archive again and overwrites the verified
file. No source archive or compiled engine is substituted by this helper.
"""
import argparse
import json
from pathlib import Path

MARKER='// Livara: build-source.sh verifies this cached archive before Surfer runs.'
ORIGINAL='    await (0, download_1.downloadFileToLocation)(url, (0, node_path_1.resolve)(constants_1.MELON_TMP_DIR, filename));'
REPLACEMENT=MARKER+'\n    if (!(0, node_fs_1.existsSync)((0, node_path_1.resolve)(constants_1.MELON_TMP_DIR, filename))) {\n'+ORIGINAL+'\n    }'


def prepare(checkout, expected_version):
    folder=checkout/'node_modules/@zen-browser/surfer'
    if json.loads((folder/'package.json').read_text())['version']!=expected_version:raise ValueError('Unexpected Surfer version; review cache patch against the new upstream')
    path=folder/'dist/commands/download/firefox.js';text=path.read_text()
    if MARKER in text:
        if text.count(REPLACEMENT)!=1:raise ValueError('Surfer cache patch is inconsistent')
        return False
    if text.count(ORIGINAL)!=1:raise ValueError('The pinned Surfer download implementation changed; no unchecked download was allowed')
    path.write_text(text.replace(ORIGINAL,REPLACEMENT));return True


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('checkout',type=Path);args=parser.parse_args()
    pin=json.loads((Path(__file__).parent/'upstream.json').read_text())
    changed=prepare(args.checkout,pin['surfer']);print('Verified source cache integration '+('applied' if changed else 'already present'))
if __name__=='__main__':main()
