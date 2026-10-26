// SPDX-License-Identifier: GPL-3.0-or-later
// Actual native app/refraction compositor test. No production screenshots.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
const out=GLib.getenv('LIVARA_GLASS_TEST_OUTPUT');
export default class Probe extends Extension{
 enable(){this.processes=[];GLib.timeout_add(GLib.PRIORITY_DEFAULT,800,()=>{this.run().catch(e=>this.finish({status:'failed',error:String(e),stack:e.stack}));return GLib.SOURCE_REMOVE;});}
 async pause(){await new Promise(r=>GLib.timeout_add(GLib.PRIORITY_DEFAULT,400,()=>{r();return GLib.SOURCE_REMOVE;}));}
 spawn(args,stdin=false){let p=Gio.Subprocess.new(args,stdin?Gio.SubprocessFlags.STDIN_PIPE:Gio.SubprocessFlags.NONE);this.processes.push(p);return p;}
 state(){try{return JSON.parse(new TextDecoder().decode(Gio.File.new_for_path(out+'/client.json').load_contents(null)[1]));}catch{return null;}}
 async shot(name){let s=Gio.File.new_for_path(out+'/'+name+'.png').replace(null,false,Gio.FileCreateFlags.REPLACE_DESTINATION,null);await new Shell.Screenshot().screenshot(false,s);s.close(null);}
 async run(){Main.overview.hide();await this.pause();
 const background=this.spawn(['python3','/project/scripts/liquid-glass-scene.py'],true);let bg;
 for(let i=0;i<30;i++){await this.pause();bg=global.get_window_actors().find(a=>a.meta_window.get_title()==='Live optical test window');if(bg)break;}
 if(!bg)throw Error('No actual Wayland scene');bg.meta_window.move_resize_frame(false,0,70,1200,800);await this.pause();
 const client=this.spawn(['/usr/bin/env','PYTHONPATH=/usr/lib/python3/dist-packages','LIVARA_DATA_DIR=/usr/share/livara','python3','/project/scripts/native-liquid-client.py'],true);
 let target,entry;const ext=Main.extensionManager.lookup('livara-glass@livara.local').stateObj;
 for(let i=0;i<40;i++){await this.pause();target=global.get_window_actors().find(a=>a.meta_window.get_wm_class()==='org.livara.Settings');entry=ext._liquid._entries.get(target);if(entry&&this.state()?.glass)break;}
 if(!entry||!this.state()?.glass)throw Error('Native handshake failed '+JSON.stringify({state:this.state(),windows:global.get_window_actors().map(a=>({c:a.meta_window.get_wm_class(),gtk:a.meta_window.get_gtk_application_id()})),entries:[...ext._liquid._entries.values()].map(e=>e.kind)}));
 target.meta_window.move_resize_frame(false,170,150,900,620);await this.pause();await this.pause();entry=ext._liquid._entries.get(target);
 if(entry.sources.has(target))throw Error('Native window captured itself');
 if(!entry.regions?.length)throw Error('Native chrome geometry was not received');
 entry.blur.radius=0;entry.effect.configure(entry.width+48,entry.height+48,entry.width,entry.height,24,0);entry.plane.queue_redraw();await this.pause();await this.shot('native-flat');
 entry.effect.configure(entry.width+48,entry.height+48,entry.width,entry.height,24,18);entry.plane.queue_redraw();await this.pause();await this.shot('native-refracted');
 bg.meta_window.move_frame(false,17,70);await this.pause();await this.shot('native-live');
 background.get_stdin_pipe().write_all(new TextEncoder().encode('change\n'),null);await this.pause();await this.shot('native-updated');
 entry.blur.radius=4;entry.plane.queue_redraw();await this.pause();await this.shot('native-material');
 const frame=target.meta_window.get_frame_rect();const report={frame:{x:frame.x,y:frame.y,width:frame.width,height:frame.height},sources:entry.sources.size,chromeRegions:entry.regions?.length,selfExcluded:!entry.sources.has(target)};
 ext._settings.set_string('appearance','light');await this.pause();await this.pause();if(!this.state()?.light)throw Error('Light appearance did not reach native glass');await this.shot('native-light');
 client.get_stdin_pipe().write_all(new TextEncoder().encode('preview\n'),null);await this.pause();await this.pause();await this.pause();
 if(!this.state()?.windows?.some(w=>w.title==='Livara Design Preview'&&w.glass))throw Error('Second native window did not receive its own material');
 if(this.state()?.windows?.some(w=>w.title==='Livara Settings'&&w.glass))throw Error('Inactive main window retained a lens');
 client.get_stdin_pipe().write_all(new TextEncoder().encode('close-preview\n'),null);await this.pause();target.meta_window.activate(global.get_current_time());await this.pause();await this.pause();
 if(!this.state()?.glass)throw Error('Main native window failed to restore after closing preview');
 ext._accessibilitySettings.set_boolean('high-contrast',true);await this.pause();await this.pause();if(this.state()?.glass)throw Error('High contrast retained clear native chrome');
 ext._accessibilitySettings.set_boolean('high-contrast',false);await this.pause();await this.pause();
 ext._settings.set_boolean('glass-enabled',false);await this.pause();await this.pause();if(this.state()?.glass)throw Error('Disabled native glass remained transparent');
 await this.shot('native-off');ext._settings.set_boolean('glass-enabled',true);await this.pause();await this.pause();if(!this.state()?.glass)throw Error('Native glass did not restore');
 ext.disable();await this.pause();await this.pause();if(this.state()?.glass)throw Error('Lost renderer retained transparent client');
 ext.enable();await this.pause();await this.pause();await this.pause();if(!this.state()?.glass)throw Error('Reenabled compositor did not restore native material');
 this.finish({status:'passed',...report,handshake:true,opaqueFallback:true,perWindowFocus:true,highContrast:true,lightAppearance:true,reload:true});}
 finish(data){Gio.File.new_for_path(out+'/native.json').replace_contents(new TextEncoder().encode(JSON.stringify(data,null,2)),null,false,Gio.FileCreateFlags.REPLACE_DESTINATION,null);for(const p of this.processes)p.force_exit();global.context.terminate();}
 disable(){}
}
