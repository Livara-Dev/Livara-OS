// Isolated contract tests for desktop integration; real GNOME qualification is separate.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
let source=fs.readFileSync('share/gnome-shell/extensions/livara-glass@livara.local/desktopTools.js','utf8').replace(/^import .*;\n/gm,'').replace('export function validatePlacements','function validatePlacements').replace('export default class DesktopTools','class DesktopTools');
source+='\nthis.DesktopTools=DesktopTools;this.validatePlacements=validatePlacements;';
let id=0;const bindings=new Map(),signals=new Map(),spawned=[];
class Emitter {connect(name,fn){const token=++id;signals.set(token,[this,name,fn]);return token;}disconnect(token){assert(signals.delete(token));}}
class Settings extends Emitter {constructor(values={}){super();this.values=values;this.settings_schema={has_key:()=>true};}get_boolean(k){return this.values[k];}set_boolean(k,v){this.values[k]=v;}get_strv(k){return this.values[k];}get_string(k){return this.values[k];}}
const gpaste=new Settings({'track-changes':true});const display=new Emitter();display.get_n_monitors=()=>2;
const session=new Emitter();Object.assign(session,{isLocked:false,isGreeter:false,hasWindows:true});
const Main={wm:{addKeybinding:(name,settings,flags,modes,fn)=>bindings.set(name,fn),removeKeybinding:name=>assert(bindings.delete(name))},overview:{hide(){}},sessionMode:session,layoutManager:{getWorkAreaForMonitor:index=>({x:index*1920,y:0,width:1920,height:1080})},notify(){}};
const tracker={get_window_app:window=>window.app?{get_id:()=>window.app}:null};
const Shell={ActionMode:{NORMAL:1,OVERVIEW:2},WindowTracker:{get_default:()=>tracker}};
let exported=false;
const Gio={DBus:{session:{}},DBusExportedObject:{wrapJSObject:()=>({export(){exported=true;},unexport(){exported=false;}})},SettingsSchemaSource:{get_default:()=>({lookup:()=>true})},Settings:function(){return gpaste;},Subprocess:{new:(argv)=>spawned.push(argv)},SubprocessFlags:{STDOUT_SILENCE:1,STDERR_SILENCE:2}};
const Meta={KeyBindingFlags:{NONE:0},WindowType:{NORMAL:0},MaximizeFlags:{BOTH:3}};
function window(app='org.livara.Studio.desktop'){return {app,monitor:1,rect:null,get_window_type:()=>0,get_transient_for:()=>null,is_on_all_workspaces:()=>false,get_stable_sequence:()=>1,get_monitor(){return this.monitor;},get_workspace:()=>({index:()=>0}),get_frame_rect:()=>({x:1920,y:0,width:960,height:1080}),get_maximized:()=>0,is_fullscreen:()=>false,unmaximize(){},move_to_monitor(n){this.monitor=n;},move_resize_frame(user,x,y,w,h){this.rect=[x,y,w,h];},change_workspace(w){this.workspace=w;},maximize(){this.maximized=true;},make_fullscreen(){this.fullscreen=true;}};}
const win=window();display.focus_window=win;
const manager={n_workspaces:1,append_new_workspace(){this.n_workspaces++;},get_workspace_by_index:i=>i};
const context={Gio,Meta,Shell,Main,global:{display,workspace_manager:manager,get_window_actors:()=>[{meta_window:win}],get_current_time:()=>123}};
vm.runInNewContext(source,context);
const settings=new Settings({'clipboard-history-enabled':false,'clipboard-excluded-apps':['org.keepassxc.KeePassXC.desktop'],'tiling-zones':'[[0,0,0.5,1],[0.5,0,0.5,1]]'});
const tools=new context.DesktopTools(settings);tools.enable();assert(exported);assert.equal(bindings.size,11);assert.equal(gpaste.get_boolean('track-changes'),false);
settings.values['clipboard-history-enabled']=true;tools.syncClipboard();assert.equal(gpaste.get_boolean('track-changes'),true);
win.app='org.keepassxc.KeePassXC.desktop';tools.syncClipboard();assert.equal(gpaste.get_boolean('track-changes'),false);
win.app=null;tools.syncClipboard();assert.equal(gpaste.get_boolean('track-changes'),false);
win.app='org.livara.Studio.desktop';session.isLocked=true;tools.syncClipboard();assert.equal(gpaste.get_boolean('track-changes'),false);
session.isLocked=false;tools.syncClipboard();assert.equal(gpaste.get_boolean('track-changes'),true);
bindings.get('zone-2')();assert.deepEqual(win.rect,[2880,0,960,1080]);
const saved=JSON.parse(tools.GetLayout());assert.equal(saved[0].app,win.app);assert.equal(saved[0].rect[2],.5);
const placement={app:win.app,ordinal:0,monitor:0,workspace:3,rect:[0,0,1,1],maximized:true,fullscreen:false};
const result=JSON.parse(tools.ApplyLayout(JSON.stringify([placement,{...placement,app:'missing.desktop'}])));assert.equal(result.applied,1);assert.equal(result.missing,1);assert.equal(manager.n_workspaces,4);assert.equal(win.workspace,3);assert.equal(win.maximized,true);
const rect=win.rect.slice();assert.throws(()=>tools.ApplyLayout(JSON.stringify([{...placement,rect:[0,0,.01,1]}])));assert.deepEqual(win.rect,rect);
for(const value of [[{...placement,command:'sh'}],[{...placement,workspace:36}],[{...placement,app:'../bad'}]])assert.throws(()=>context.validatePlacements(value));
manager.n_workspaces=1;manager.append_new_workspace=()=>{};assert.equal(JSON.parse(tools.ApplyLayout(JSON.stringify([placement]))).missing,1);
settings.values['tiling-zones']='malformed';assert.equal(JSON.parse(tools.GetStatus()).zones,0);
tools.disable();assert.equal(bindings.size,0);assert.equal(signals.size,0);assert.equal(exported,false);assert.equal(gpaste.get_boolean('track-changes'),false);
console.log('PASS: 11 shortcut bindings, focus/lock/exclusion filters, multi-monitor zones, validated layouts, missing apps, bounded workspaces, cleanup');
