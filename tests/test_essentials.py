import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
from livara import essentials as features, theme, palette, install_config

class EssentialsTests(unittest.TestCase):
    def test_zones_boundaries(self):
        self.assertEqual(features.validate_zones([[0,0,1,1]]),[[0,0,1,1]])
        for value in ([],[[0,0,0,1]],[[.9,0,.2,1]],[[float('nan'),0,.5,1]],[[True,0,.5,1]],[[0,0,.5,1]]*10):
            with self.assertRaises(ValueError):features.validate_zones(value)
    def placement(self):
        return {'preferences':{},'windows':[{'app':'org.livara.Studio.desktop','ordinal':0,'workspace':1,'monitor':0,'rect':[0,0,.5,1],'maximized':False,'fullscreen':False}]}
    def test_layout_rejects_private_settings_and_commands(self):
        item=self.placement();features.validate_layout(item)
        item['preferences']={'remember-recent-files':True}
        with self.assertRaises(ValueError):features.validate_layout(item)
        item=self.placement();item['windows'][0]['command']='sh'
        with self.assertRaises(ValueError):features.validate_layout(item)
        item=self.placement();item['windows'][0]['workspace']=100
        with self.assertRaises(ValueError):features.validate_layout(item)
    def test_store_private_atomic_and_inert(self):
        with tempfile.TemporaryDirectory() as folder:
            store=features.NamedStore('themes',theme.validate,folder)
            store.save('بنفش',{'theme-accent':'#aa99ff'})
            self.assertEqual(store.list()['بنفش']['theme-accent'],'#aa99ff')
            self.assertEqual(stat.S_IMODE(store.path.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(store.folder.stat().st_mode),0o700)
            original=store.path.read_bytes()
            with self.assertRaises(ValueError):store.save('bad',{'command':'sh'})
            self.assertEqual(store.path.read_bytes(),original)
            store.delete('بنفش');self.assertEqual(store.list(),{})
    def test_store_symlink_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            store=features.NamedStore('themes',theme.validate,folder);store.save('a',{})
            store.path.write_text('{"a":{},"a":{}}')
            with self.assertRaises(ValueError):store.list()
            store.path.unlink();outside=Path(folder)/'outside';outside.write_text('{}');store.path.symlink_to(outside)
            with self.assertRaises(OSError):store.list()
            self.assertEqual(outside.read_text(),'{}')
    def test_theme_css_validation_and_preservation(self):
        for value in ({'theme-accent':'red; * {color:red}'},{'theme-radius':True},{'theme-opacity':101},{'run':'evil'}):
            with self.assertRaises(ValueError):theme.validate(value)
        self.assertEqual(theme.css({}),'')
        css=theme.css({'theme-enabled':True},motion=False)
        self.assertIn('0ms',css);self.assertIn('#c5a3ff',css)
        existing='/* user */\nbutton { padding: 10px; }\n'
        modified=theme.replace_block(existing,css)
        self.assertEqual(theme.replace_block(modified,''),existing)
        self.assertEqual(theme.replace_block(modified,css),modified)
        with self.assertRaises(ValueError):theme.replace_block(theme.BEGIN,'')
    def test_theme_bundle_visual_only_and_no_executable_data(self):
        value={'tokens':{'theme-accent':'#be83ff'},'preferences':{'glass-enabled':True,'interface-font':'Livara Sans 11'},'extras':{'icons':'Adwaita','sounds':'freedesktop','event-sounds':False}}
        self.assertTrue(features.validate_theme_bundle(value)['preferences']['glass-enabled'])
        for field,item in [('preferences',{'screen-lock':False}),('extras',{'icons':'../escape'}),('extras',{'run':'sh'}),('extras',{'event-sounds':'yes'})]:
            with self.assertRaises(ValueError):features.validate_theme_bundle({**value,field:item})
    def test_theme_preflights_missing_theme_before_any_write(self):
        value={'tokens':{},'preferences':{},'extras':{'icons':'Missing'}}
        with patch.object(features,'installed_theme_names',return_value=[]),patch.object(features.desktop,'_apply_options') as write:
            with self.assertRaises(ValueError):features.apply_theme_bundle(value)
            write.assert_not_called()
    def test_theme_snapshot_omits_foreign_values(self):
        with patch.object(features.desktop,'read_option',side_effect=lambda key: 'appmenu:close' if key=='window-buttons' else None):
            self.assertNotIn('window-buttons',features.appearance_snapshot())
    def test_theme_snapshot_does_not_reapply_removed_themes(self):
        settings=Mock()
        settings.get_value.side_effect=lambda key: Mock(unpack=lambda: False if key=='event-sounds' else 'RemovedTheme')
        with patch.object(features,'appearance_snapshot',return_value={}), \
             patch.object(features.desktop,'settings_for',return_value=settings), \
             patch.object(features,'installed_theme_names',return_value=['Adwaita']):
            snapshot=features.current_theme_bundle(tokens={'theme-accent':'#be83ff'})
        self.assertEqual(snapshot['extras'],{'event-sounds':False})
    def test_permissions_exact_safe_argv(self):
        self.assertEqual(features.permission_command('org.test.App','home',False),['flatpak','override','--user','--nofilesystem=home','org.test.App'])
        for app,permission,allowed in [('--bad','network',True),('org.App','camera',True),('org.App','network',1),('org.App\n','home',False)]:
            with self.assertRaises(ValueError):features.permission_command(app,permission,allowed)
    def test_profile_reports_unavailable_power_and_previous(self):
        with patch.object(features.desktop,'read_option',return_value=True),patch.object(features.desktop,'_apply_options',return_value={'applied':3}),patch.object(features,'power_state',side_effect=ValueError('No power service')):
            result=features.apply_profile('Gaming')
            self.assertIn('Unavailable',result['power']);self.assertTrue(result['previous']['glass-enabled'])
    def test_lab_real_private_project(self):
        with tempfile.TemporaryDirectory() as folder:
            path=features.create_lab('test-lab',Path(folder))
            self.assertTrue((path/'case.json').is_file());self.assertTrue((path/'work').is_dir())
            self.assertIn('Authorized systems', (path/'notes/scope.md').read_text())
            self.assertEqual(stat.S_IMODE((path/'notes/scope.md').stat().st_mode),0o600)
    def test_palette_file_bounds_and_no_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'Documents';path.mkdir()
            for name in ('one.txt','two.txt','.secret'): (path/name).write_text('x')
            (path/'link').symlink_to(path/'one.txt')
            self.assertEqual(len(palette.local_files(folder)),2)
            self.assertLessEqual(len(palette.local_files(folder,1)),1)
    def test_palette_search_and_real_routes(self):
        entries=palette.commands();self.assertTrue(any(e['argv']==['livara-studio','--tool','json'] for e in entries))
        self.assertTrue(any(e['argv']==['livara-essentials','--page','theme'] for e in entries))
        found=palette.search(entries,'app icons');self.assertEqual(found[0]['name'],'Change app icons')
        self.assertEqual(palette.search(entries,'x'*257),[])
    def test_layout_missing_shell_does_not_save_fake(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(features.desktop,'read_option',return_value=None):
            store=features.NamedStore('layouts',features.validate_layout,folder)
            with self.assertRaises(RuntimeError):features.save_layout('test',store=store,capture=lambda method:(_ for _ in ()).throw(RuntimeError('No Shell')))
            self.assertEqual(store.list(),{})
    def test_diagnostic_missing_command(self):
        self.assertFalse(features.diagnostic(['livara-never-installed-command'])['available'])

class InstallerTargetTests(unittest.TestCase):
    def fixture(self,root):
        for name in ('etc/gdm3','usr/lib','etc/sudoers.d','home/alice/.config/autostart','etc/skel/.config/autostart'):(root/name).mkdir(parents=True)
        (root/'usr/lib/os-release').write_text('ID=livara\n')
        (root/'etc/os-release').symlink_to('../usr/lib/os-release')
        (root/'etc/passwd').write_text('root:x:0:0:root:/root:/bin/bash\nalice:x:1000:1000:Alice:/home/alice:/bin/bash\n')
        (root/'etc/gdm3/custom.conf').write_text('[daemon]\nAutomaticLoginEnable=true\nAutomaticLogin=livara\n')
        (root/'etc/subuid').write_text('existing:100000:65536\n')
        (root/'etc/sudoers.d/casper').write_text('ALL ALL=(ALL) NOPASSWD: ALL\n')
        (root/'home/alice/.config/autostart/livara-live-session.desktop').write_text('live')
    def test_target_only_idempotent_finalizer(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root)
            result=install_config.finalize_target(root);self.assertEqual(result['users'],['alice'])
            self.assertIn('AutomaticLoginEnable = false',(root/'etc/gdm3/custom.conf').read_text())
            self.assertNotIn('AutomaticLogin =',(root/'etc/gdm3/custom.conf').read_text())
            self.assertFalse((root/'etc/sudoers.d/casper').exists());self.assertFalse((root/'home/alice/.config/autostart/livara-live-session.desktop').exists())
            self.assertIn('alice:165536:65536',(root/'etc/subuid').read_text())
            before=(root/'etc/subuid').read_bytes();install_config.finalize_target(root);self.assertEqual(before,(root/'etc/subuid').read_bytes())
    def test_refuse_host_and_foreign_target(self):
        with self.assertRaises(ValueError):install_config.finalize_target('/')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root);(root/'usr/lib/os-release').write_text('ID=ubuntu\n')
            with self.assertRaises(ValueError):install_config.finalize_target(root)
            self.assertTrue((root/'etc/sudoers.d/casper').exists())
    def test_symlink_escape_preflight_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder,tempfile.TemporaryDirectory() as outside:
            root=Path(folder);self.fixture(root);(root/'etc/subgid').symlink_to(Path(outside)/'escape')
            before=(root/'etc/gdm3/custom.conf').read_bytes()
            with self.assertRaises(ValueError):install_config.finalize_target(root)
            self.assertEqual(before,(root/'etc/gdm3/custom.conf').read_bytes());self.assertFalse((Path(outside)/'escape').exists())

if __name__=='__main__':unittest.main()
