# SPDX-License-Identifier: GPL-3.0-or-later
import libcalamares
from livara.install_config import finalize_target

def pretty_name(): return 'Preparing your Livara desktop'
def run():
    try: finalize_target(libcalamares.globalstorage.value('rootMountPoint'))
    except Exception as error: return ('Livara target configuration failed', str(error))
    return None
