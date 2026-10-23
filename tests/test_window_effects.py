"""Window-manager state-machine checks against the production GNOME extension."""
from pathlib import Path
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
EFFECTS = ROOT / 'share/gnome-shell/extensions/livara-glass@livara.local/windowEffects.js'

NODE = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8').replace(/^import .*;\n/gm,'').replace('export default class WindowEffects','class WindowEffects')+'\nthis.WindowEffects=WindowEffects;';
let next=1;
class Emitter {
 constructor(){this.signals=new Map();}
 connect(name,callback){const id=next++;this.signals.set(id,{name,callback,blocks:0});return id;}
 disconnect(id){assert(this.signals.has(id));this.signals.delete(id);}
 emit(name,...args){for(const item of [...this.signals.values()])if(item.name===name&&!item.blocks)item.callback(this,...args);}
}
class ShellWM extends Emitter {
 constructor(){super();this.maps=new Map();this.destroys=new Map();}
 completed_map(actor){this.maps.set(actor,(this.maps.get(actor)||0)+1);}
 completed_destroy(actor){this.destroys.set(actor,(this.destroys.get(actor)||0)+1);}
}
class NativeWM {
 constructor(shell){this._shellwm=shell;this.mapBook=0;this.destroyBook=0;this.nativeAnimations=0;this.shouldChecks=0;
 this.mapId=shell.connect('map',this._mapWindow.bind(this));this.destroyId=shell.connect('destroy',this._destroyWindow.bind(this));}
 _shouldAnimateActor(actor){this.shouldChecks++;return actor.canAnimate!==false;}
 async _mapWindow(shell,actor){this.mapBook++;if(actor.failMap)throw new Error('map fixture failure');
 if(actor.other){assert(this._shouldAnimateActor(actor.other,[0]));shell.completed_map(actor.other);}
 if(!this._shouldAnimateActor(actor,[0])){shell.completed_map(actor);return;}
 await Promise.resolve();this.nativeAnimations++;actor.ease({opacity:255,onStopped:()=>shell.completed_map(actor)});}
 _destroyWindow(shell,actor){this.destroyBook++;if(actor.failDestroy)throw new Error('destroy fixture failure');
 if(!this._shouldAnimateActor(actor,[0])){shell.completed_destroy(actor);return;}
 this.nativeAnimations++;actor.ease({opacity:0,onStopped:()=>shell.completed_destroy(actor)});}
}
class Actor extends Emitter {
 constructor(options={}){super();this.opacity=255;this.scale_x=1;this.scale_y=1;this.translation_y=0;this.pivot=[0,0];this.calls=[];this.shown=0;
 this.meta_window={get_window_type:()=>options.type||0,get_transient_for:()=>options.transient||null,is_attached_dialog:()=>!!options.attached,is_fullscreen:()=>!!options.fullscreen};Object.assign(this,options);}
 get_pivot_point(){return [...this.pivot];}set_pivot_point(x,y){this.pivot=[x,y];}show(){this.shown++;}
 ease(params){if(this.failEase)throw new Error('ease fixture failure');this.calls.push(params);this.transition=params;}
 remove_transition(){if(this.transition){const old=this.transition;this.transition=null;old.onStopped?.();}}
 finish(){const old=this.transition;this.transition=null;if(old){for(const[key,value]of Object.entries(old))if(!['duration','mode','onStopped'].includes(key))this[key]=value;old.onStopped?.();}}
}
class Settings extends Emitter {constructor(values){super();this.values=values;}get_boolean(key){return this.values[key];}get_int(key){return this.values[key];}get_string(key){return this.values[key];}}
function setup(options={}){
 const shell=new ShellWM(),wm=new NativeWM(shell),overview=new Emitter(),session=new Emitter();session.hasWindows=true;
 const settings=new Settings({'window-animation-style':'zoom','window-animation-duration':220}),ui=new Settings({'enable-animations':true});
 const GObject={signal_handler_find:(object,match)=>options.missing===match.signalId?0:[...object.signals].find(([,item])=>item.name===match.signalId)?.[0],
 signal_handler_block:(object,id)=>object.signals.get(id).blocks++,signal_handler_unblock:(object,id)=>object.signals.get(id).blocks--,
 signal_handler_is_connected:(object,id)=>object.signals.has(id)};
 const sandbox={console:{warn(){}},GObject,Meta:{WindowType:{NORMAL:0}},Clutter:{AnimationMode:{EASE_OUT_CUBIC:1,EASE_IN_QUAD:2}},Main:{wm,overview,sessionMode:session},global:{window_manager:shell}};
 vm.createContext(sandbox);vm.runInContext(source,sandbox);const engine=new sandbox.WindowEffects(settings,ui);
 return {engine,settings,ui,shell,wm,overview,session,GObject};
}
const count=(shell,kind,actor)=>(kind==='map'?shell.maps:shell.destroys).get(actor)||0;
async function run(name){
 if(name==='styles'){
  for(const style of ['zoom','lift','fade']){const s=setup();s.settings.values['window-animation-style']=style;assert(s.engine.enable());
   const should=s.wm._shouldAnimateActor,complete=s.shell.completed_map;
   for(const kind of ['map','destroy']){const actor=new Actor();s.shell.emit(kind,actor);assert.equal(count(s.shell,kind,actor),0);assert.equal(s.engine._active.size,1);
    const effect=actor.calls.at(-1);assert.equal(effect.duration,220);assert.equal(effect.opacity,kind==='map'?255:0);
    if(style==='zoom')assert.equal(kind==='map'?actor.scale_x:effect.scale_x,kind==='map'?.92:.94);
    if(style==='lift')assert.equal(kind==='map'?actor.translation_y:effect.translation_y,kind==='map'?18:12);
    if(style==='fade')assert.equal(effect.scale_x,undefined);
    actor.finish();assert.equal(count(s.shell,kind,actor),1);assert.equal(s.engine._active.size,0);assert.equal(actor.opacity,255);assert.equal(actor.scale_x,1);assert.equal(actor.translation_y,0);assert.deepEqual(actor.pivot,[0,0]);
    effect.onStopped();assert.equal(count(s.shell,kind,actor),1);
   }assert.equal(s.wm._shouldAnimateActor,should);assert.equal(s.shell.completed_map,complete);assert.equal(s.wm.mapBook,1);assert.equal(s.wm.destroyBook,1);assert.equal(s.wm.nativeAnimations,0);s.engine.disable();}
 }else if(name==='cancel'){
  const s=setup();s.engine.enable();const actor=new Actor();s.shell.emit('map',actor);const stopped=actor.calls[0].onStopped;
  s.shell.emit('kill-window-effects',actor);stopped();s.engine.disable();assert.equal(count(s.shell,'map',actor),1);assert.equal(actor.opacity,255);assert.equal(s.shell.signals.get(s.wm.mapId).blocks,0);
  const t=setup();t.engine.enable();const custom=new Actor({opacity:0,scale_x:.83,scale_y:1.27,translation_y:7,pivot:[.1,.9]});t.shell.emit('destroy',custom);t.shell.emit('kill-window-effects',custom);
  assert.equal(custom.opacity,0);assert.equal(custom.scale_x,.83);assert.equal(custom.scale_y,1.27);assert.equal(custom.translation_y,7);assert.deepEqual(custom.pivot,[.1,.9]);assert.equal(count(t.shell,'destroy',custom),1);t.engine.disable();
 }else if(name==='disable'){
  const s=setup();s.engine.enable();const first=new Actor(),second=new Actor();s.shell.emit('map',first);s.shell.emit('destroy',second);s.engine.disable();
  assert.equal(count(s.shell,'map',first),1);assert.equal(count(s.shell,'destroy',second),1);assert.equal(s.engine._active.size,0);assert.equal(s.shell.signals.size,2);
  const actor=new Actor();s.shell.emit('map',actor);await Promise.resolve();actor.finish();assert.equal(s.wm.nativeAnimations,1);assert.equal(count(s.shell,'map',actor),1);
 }else if(name==='policy'){
  for(const mode of ['off','motion','locked','greeter','overview','nosession','nativeSkip']){const s=setup();s.engine.enable();const actor=new Actor();
   if(mode==='off')s.settings.values['window-animation-style']='off';if(mode==='motion')s.ui.values['enable-animations']=false;
   if(mode==='locked')s.session.isLocked=true;if(mode==='greeter')s.session.isGreeter=true;if(mode==='overview')s.overview.visibleTarget=true;if(mode==='nosession')s.session.hasWindows=false;if(mode==='nativeSkip')actor.canAnimate=false;
   s.shell.emit('map',actor);assert.equal(actor.calls.length,0);assert.equal(count(s.shell,'map',actor),1);s.engine.disable();}
  for(const change of ['motion','style','overview','lock']){const s=setup();s.engine.enable();const actor=new Actor();s.shell.emit('map',actor);
   if(change==='motion'){s.ui.values['enable-animations']=false;s.ui.emit('changed::enable-animations');}if(change==='style')s.settings.emit('changed','window-animation-style');
   if(change==='overview')s.overview.emit('showing');if(change==='lock'){s.session.isLocked=true;s.session.emit('updated');}
   assert.equal(count(s.shell,'map',actor),1);assert.equal(s.engine._active.size,0);s.engine.disable();}
 }else if(name==='native'){
  for(const options of [{type:1},{fullscreen:true},{transient:{}},{attached:true}]){const s=setup();s.engine.enable();const actor=new Actor(options);s.shell.emit('map',actor);await Promise.resolve();assert.equal(s.engine._active.size,0);assert.equal(s.wm.nativeAnimations,1);actor.finish();assert.equal(count(s.shell,'map',actor),1);s.engine.disable();}
  const s=setup();s.engine.enable();const other=new Actor(),actor=new Actor({other});s.shell.emit('map',actor);assert.equal(count(s.shell,'map',other),1);assert.equal(count(s.shell,'map',actor),0);actor.finish();s.engine.disable();
 }else if(name==='failures'){
  for(const option of ['failMap','failDestroy','failEase']){const s=setup();s.engine.enable();const actor=new Actor({[option]:true});const kind=option==='failDestroy'?'destroy':'map';s.shell.emit(kind,actor);await Promise.resolve();await Promise.resolve();assert.equal(count(s.shell,kind,actor),1);assert.equal(s.engine._active.size,0);s.engine.disable();}
  const s=setup({missing:'destroy'});assert.equal(s.engine.enable(),false);assert.equal(s.shell.signals.get(s.wm.mapId).blocks,0);
  const incompatible=setup();Object.defineProperty(incompatible.shell,'completed_map',{value:incompatible.shell.completed_map,writable:false,configurable:false});assert.equal(incompatible.engine.enable(),false);assert.equal(incompatible.shell.signals.get(incompatible.wm.mapId).blocks,0);
 }else if(name==='destroyed'){
  const s=setup();s.engine.enable();const actor=new Actor();s.shell.emit('destroy',actor);const stopped=actor.calls[0].onStopped;actor.emit('destroy');stopped();assert.equal(count(s.shell,'destroy',actor),1);assert.equal(s.engine._active.size,0);s.engine.disable();
 }else if(name==='bounds'){
  const s=setup();s.engine.enable();s.settings.values['window-animation-duration']=99999;const actors=Array.from({length:13},()=>new Actor());for(const actor of actors)s.shell.emit('map',actor);
  assert.equal(s.engine._active.size,12);assert.equal(count(s.shell,'map',actors[12]),1);assert.equal(actors[0].calls[0].duration,600);s.engine._finishAll();
  s.settings.values['window-animation-duration']=0;const actor=new Actor();s.shell.emit('map',actor);assert.equal(actor.calls[0].duration,80);s.engine.disable();for(const item of actors)assert.equal(count(s.shell,'map',item),1);
 }else throw new Error('unknown case');
}
run(process.argv[2]).then(()=>process.stdout.write('PASS\n')).catch(error=>{console.error(error);process.exitCode=1;});
'''


@unittest.skipUnless(shutil.which('node'), 'Node is required for the compositor state-machine fixtures')
class WindowEffects(unittest.TestCase):
    def check_case(self, case):
        result = subprocess.run(['node', '-e', NODE, str(EFFECTS), case], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS')

    def test_styles_finish_once_and_preserve_native_bookkeeping(self): self.check_case('styles')
    def test_kill_cancellation_and_stopped_callback_complete_once(self): self.check_case('cancel')
    def test_disable_finishes_operations_and_restores_original_handlers(self): self.check_case('disable')
    def test_reduced_motion_off_overview_lock_and_live_policy_changes(self): self.check_case('policy')
    def test_dialogs_fullscreen_transients_and_other_actors_keep_native_paths(self): self.check_case('native')
    def test_bookkeeping_transition_and_api_failures_do_not_hold_windows(self): self.check_case('failures')
    def test_destroyed_actor_is_completed_once(self): self.check_case('destroyed')
    def test_duration_and_concurrent_actor_limits(self): self.check_case('bounds')

    def test_window_schema_keys_defaults_and_ranges(self):
        schema = ET.parse(ROOT / 'share/livara/org.livara.desktop.gschema.xml').getroot().find('schema')
        keys = {key.attrib['name']: key for key in schema.findall('key')}
        self.assertEqual(keys['window-animation-style'].find('default').text, "'zoom'")
        self.assertEqual({choice.attrib['value'] for choice in keys['window-animation-style'].find('choices')}, {'zoom', 'lift', 'fade', 'off'})
        self.assertEqual(keys['window-animation-duration'].find('range').attrib, {'min': '80', 'max': '600'})
        self.assertEqual(keys['window-button-size'].find('range').attrib, {'min': '10', 'max': '22'})
        self.assertEqual(keys['window-green-action'].find('default').text, "'fullscreen'")
        for key in ['window-button-style', 'window-button-symbols', 'window-close-color', 'window-minimize-color', 'window-maximize-color']:
            self.assertIn(key, keys)


if __name__ == '__main__':
    unittest.main()
