"""Target-only installation finalizer. No partitioning or host command execution."""
from __future__ import annotations
import configparser
import os
from pathlib import Path
import re
import tempfile


def finalize_target(directory):
    root=Path(directory)
    if not root.is_absolute() or root.is_symlink():raise ValueError('An absolute mounted target is required')
    root=root.resolve()
    if root==Path('/') or not root.is_dir():raise ValueError('Refusing to configure the running system')
    def target(relative):
        path=root/relative
        # Refuse symlinks at every component, even a currently broken link.
        current=root
        for part in Path(relative).parts:
            if part in ('..','/'):raise ValueError('Invalid target path')
            current=current/part
            if current.is_symlink():raise ValueError('Target path contains a symbolic link: '+relative)
        if not path.resolve().is_relative_to(root):raise ValueError('Target path escapes installation root')
        return path
    release=target('usr/lib/os-release')
    if not release.exists():release=target('etc/os-release')
    if not release.is_file() or not re.search(r'^ID=[\"\']?livara[\"\']?$',release.read_text(),re.M):raise ValueError('The target is not Livara')
    passwd=target('etc/passwd').read_text().splitlines()
    users=[]
    for row in passwd:
        fields=row.split(':')
        if len(fields)!=7:raise ValueError('Invalid target account database')
        if fields[2].isdigit() and 1000<=int(fields[2])<60000 and fields[6] not in ('/usr/sbin/nologin','/bin/false'):
            if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}',fields[0]):raise ValueError('Invalid account name')
            home=Path(fields[5])
            if not home.is_absolute() or not home.is_relative_to('/home') or len(home.parts)!=3:raise ValueError('Expected a normal target home')
            target(str(home).lstrip('/'));users.append((fields[0],str(home).lstrip('/')))
    if not users:raise ValueError('Create a persistent local account before finalizing')
    plans={};removals=[]
    gdm=target('etc/gdm3/custom.conf');parser=configparser.ConfigParser();parser.optionxform=str
    if gdm.exists():parser.read_string(gdm.read_text())
    if not parser.has_section('daemon'):parser.add_section('daemon')
    parser.set('daemon','AutomaticLoginEnable','false');parser.remove_option('daemon','AutomaticLogin');parser.remove_option('daemon','TimedLogin');parser.set('daemon','TimedLoginEnable','false')
    import io
    stream=io.StringIO();parser.write(stream);plans['etc/gdm3/custom.conf']=stream.getvalue()
    for home in ['etc/skel']+[home for user,home in users]:
        for file in ('livara-live-session.desktop','org.livara.Center.desktop'):
            removals.append(target(home+'/.config/autostart/'+file))
    # Casper's broad live-session sudo grant must never survive installation.
    removals.append(target('etc/sudoers.d/casper'))
    plans['etc/update-manager/release-upgrades']='[DEFAULT]\nPrompt=never\n'
    for file in ('subuid','subgid'):
        path=target('etc/'+file);original=path.read_text() if path.exists() else '';ranges=[];assigned=set()
        for line in original.splitlines():
            if not line or line.startswith('#'):continue
            parts=line.split(':')
            if len(parts)!=3 or not parts[1].isdigit() or not parts[2].isdigit():raise ValueError('Invalid subordinate ID database')
            start,count=int(parts[1]),int(parts[2]);ranges.append((start,start+count));assigned.add(parts[0])
        lines=[];next_id=100000
        for user,home in users:
            if user in assigned:continue
            while any(next_id<end and next_id+65536>start for start,end in ranges):
                next_id=max(end for start,end in ranges if next_id<end and next_id+65536>start)
            if next_id+65536>2**32:raise ValueError('No subordinate ID range is available')
            lines.append(f'{user}:{next_id}:65536');ranges.append((next_id,next_id+65536));next_id+=65536
        plans['etc/'+file]=original+('' if not original or original.endswith('\n') else '\n')+''.join(line+'\n' for line in lines)
    plans['etc/livara-installed']='Livara installation finalized; disk boot and recovery qualification are separate.\n'
    # Preflight ALL paths before writing anything, including parent ownership links.
    for relative in plans:target(relative)
    for relative,data in plans.items():
        path=target(relative);path.parent.mkdir(parents=True,exist_ok=True)
        fd,temporary=tempfile.mkstemp(dir=path.parent,prefix='.livara-install-')
        try:
            with os.fdopen(fd,'w') as handle:handle.write(data);handle.flush();os.fsync(handle.fileno())
            os.chmod(temporary,0o644);os.replace(temporary,path)
        finally:Path(temporary).unlink(missing_ok=True)
    for path in removals:path.unlink(missing_ok=True)
    return {'users':[user for user,home in users],'autologin':False,'target':str(root)}
