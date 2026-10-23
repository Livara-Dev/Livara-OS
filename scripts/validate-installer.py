#!/usr/bin/env python3
"""Validate Livara's installer against the installed Calamares module schemas.
Read-only. Requires python3-yaml/jsonschema and the actual Noble Calamares package.
"""
import argparse
import json
from pathlib import Path
import sys
import yaml
import jsonschema
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--modules',type=Path,default=Path('/usr/lib/x86_64-linux-gnu/calamares/modules'));args=parser.parse_args()
checks=[];errors=[]
for path in sorted((root/'share/calamares/modules').glob('*.conf')):
    value=yaml.safe_load(path.read_text());schema=args.modules/path.stem/(path.stem+'.schema.yaml')
    if not isinstance(value,dict):raise ValueError('Invalid configuration: '+path.name)
    if schema.is_file():
        jsonschema.validate(value,yaml.safe_load(schema.read_text()));checks.append(path.name+': upstream schema passed')
    else:checks.append(path.name+': YAML parsed; this packaged module has no schema')
settings=yaml.safe_load((root/'share/calamares/settings.conf').read_text())
for stage in settings['sequence']:
    for modules in stage.values():
        for name in modules:
            if name=='livara':continue
            if not (args.modules/name/'module.desc').is_file():errors.append('Missing actual module: '+name)
exec_modules=next(stage['exec'] for stage in settings['sequence'] if 'exec' in stage)
assert 'luksbootkeyfile' not in exec_modules
assert exec_modules.index('users')<exec_modules.index('livara')<exec_modules.index('initramfs')
assert yaml.safe_load((root/'share/calamares/modules/fstab.conf').read_text())['crypttabOptions']=='luks'
checks.append('Real module inventory and safe finalizer/encryption order checked')
print(json.dumps({'checks':checks,'errors':errors,'end_to_end_disk_install_qualified':False},indent=2))
raise SystemExit(bool(errors))
