"""Exercise shell-material discovery, cleanup and texture bounds without a compositor."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / 'share/gnome-shell/extensions/livara-glass@livara.local/extension.js'
NODE = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let svg='',textureSize=[],removed=0;
const sandbox={Extension:class{},TextEncoder,console,Shell:{BlurMode:{BACKGROUND:1},BlurEffect:class{}},
 Clutter:{ContentGravity:{RESIZE_FILL:2},Image:class{set_data(...args){this.data=args;}}},
 Cogl:{PixelFormat:{RGBA_8888:1}},GLib:{source_remove(){removed++;}},
 GdkPixbuf:{PixbufLoader:{new_with_type(){return{set_size(w,h){textureSize=[w,h];},write(bytes){svg=new TextDecoder().decode(bytes);},close(){},get_pixbuf(){return {width:textureSize[0],height:textureSize[1],rowstride:textureSize[0]*4,get_pixels(){return [];}};}};}}}};
vm.createContext(sandbox);
const source=fs.readFileSync(process.argv[1],'utf8').replace(/^import .*;\n/gm,'').replace('export default class LivaraGlass','class LivaraGlass')+'\nthis.LivaraGlass=LivaraGlass;';
vm.runInContext(source,sandbox);
const engine=new sandbox.LivaraGlass();engine._surfaces=new Map();engine._material=true;engine._radius=24;
class Actor {
 constructor(cls){this.cls=cls;this.content=null;this.content_gravity=7;this.width=1200;this.height=600;this.mapped=true;this.effects=[];}
 has_style_class_name(cls){return this.cls===cls;}connect(){return 1;}disconnect(){}
 add_effect_with_name(name,effect){this.effects.push(effect);}remove_effect(effect){this.effects=this.effects.filter(e=>e!==effect);}
}
for(const [cls,kind]of [['dash-background','dock'],['popup-menu-content','menu'],['notification-banner','notification'],['osd-window','osd'],['modal-dialog','dialog']]){
 const actor=new Actor(cls);engine._classify(actor);const state=engine._surfaces.get(actor);assert.equal(state.kind,kind);assert.equal(actor.effects.length,1);
 assert(textureSize.every(size=>size<=512));assert(!svg.includes('NaN'));assert(svg.includes('id="lens"'));assert(svg.includes('id="caustic"'));assert.notEqual(actor.content,null);
 const rim=actor.content;engine._syncSurface(actor);assert.equal(actor.content,rim); // cached between allocations
 actor.mapped=false;engine._syncSurface(actor);assert.equal(actor.effects.length,0);assert.equal(actor.content,null);assert.equal(actor.content_gravity,7);
 actor.mapped=true;engine._material=false;engine._syncSurface(actor);assert.equal(actor.effects.length,0);assert.equal(actor.content,null);
 engine._material=true;engine._syncSurface(actor);assert.equal(actor.effects.length,1);engine._removeSurface(actor);assert.equal(actor.effects.length,0);assert.equal(actor.content,null);
}
const foreign=new Actor('popup-menu-content');foreign.content={owner:'another-extension'};engine._classify(foreign);assert.equal(foreign.content.owner,'another-extension');engine._removeSurface(foreign);assert.equal(foreign.content.owner,'another-extension');
for(let i=0;i<30;i++)engine._classify(new Actor('osd-window'));assert.equal(engine._surfaces.size,24);
const first=engine._surfaces.keys().next().value;engine._radius=0;engine._syncSurface(first);assert.equal(first.effects.length,0);
process.stdout.write('PASS: five shell material surfaces, caching, 512px textures, cleanup, foreign content and 24-surface bound\n');
'''


@unittest.skipUnless(shutil.which('node'), 'Node is required for shell material fixtures')
class GlassMaterial(unittest.TestCase):
    def test_discovery_cached_lenses_policy_and_cleanup(self):
        result = subprocess.run(['node', '-e', NODE, str(EXTENSION)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS:', result.stdout)
