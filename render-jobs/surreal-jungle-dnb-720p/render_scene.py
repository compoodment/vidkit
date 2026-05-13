#!/usr/bin/env python3
"""Surreal Jungle DnB 720p procedural Blender render.
Run inside Blender: blender -b --python render_scene.py -- <out_dir>
"""

import math, os, sys, shutil, subprocess
from pathlib import Path
import bpy
from mathutils import Vector

FPS = int(os.environ.get("VIDKIT_FPS", "24"))
DURATION = float(os.environ.get("VIDKIT_DURATION", "120"))
WIDTH = int(os.environ.get("VIDKIT_WIDTH", "1280"))
HEIGHT = int(os.environ.get("VIDKIT_HEIGHT", "720"))
SAMPLES = int(os.environ.get("VIDKIT_SAMPLES", "128"))
DEVICE = os.environ.get("VIDKIT_CYCLES_DEVICE", "CUDA").upper()
OUT_DIR = Path(sys.argv[-1]) if len(sys.argv) > 1 and not sys.argv[-1].startswith("-") else Path("outputs/surreal-jungle-dnb-720p")
FRAMES_DIR = OUT_DIR / "frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)
TOTAL = int(round(FPS * DURATION))

SCENES = [
    (0, 12, "blue data tunnel"),
    (12, 27, "alien temple portal"),
    (27, 42, "orange green jungle"),
    (42, 57, "desert data mirage"),
    (57, 72, "checkerboard gallery"),
    (72, 87, "candy snow shrine"),
    (87, 105, "biome collision peak"),
    (105, 120, "temple ascension"),
]

def frame(t): return int(round(t * FPS)) + 1

def hex_rgba(h, a=1):
    h=str(h).strip().lstrip('#')
    if len(h)==3: h=''.join(c*2 for c in h)
    return (int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255, a)

def mat(name, color, metallic=0, roughness=0.35, emission=None, strength=0):
    m=bpy.data.materials.new(name); m.use_nodes=True
    bsdf=m.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        if 'Base Color' in bsdf.inputs: bsdf.inputs['Base Color'].default_value=hex_rgba(color)
        if 'Metallic' in bsdf.inputs: bsdf.inputs['Metallic'].default_value=metallic
        if 'Roughness' in bsdf.inputs: bsdf.inputs['Roughness'].default_value=roughness
        if emission:
            if 'Emission Color' in bsdf.inputs: bsdf.inputs['Emission Color'].default_value=hex_rgba(emission)
            elif 'Emission' in bsdf.inputs:
                try: bsdf.inputs['Emission'].default_value=hex_rgba(emission)
                except Exception: pass
            if 'Emission Strength' in bsdf.inputs: bsdf.inputs['Emission Strength'].default_value=strength
    return m

def checker_mat(name):
    m=bpy.data.materials.new(name); m.use_nodes=True
    nt=m.node_tree; bsdf=nt.nodes.get('Principled BSDF')
    tex=nt.nodes.new('ShaderNodeTexChecker'); tex.inputs['Scale'].default_value=10
    tex.inputs['Color1'].default_value=(0.02,0.02,0.025,1); tex.inputs['Color2'].default_value=(0.92,0.86,0.72,1)
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value=0.18
    return m

M={
 'blackglass': mat('black alien glass','#04030b',0.05,0.08),
 'chrome': mat('mirror chrome','#dff7ff',1,0.035),
 'blue': mat('electric blue','#071d42',0,0.2,'#00aaff',2.8),
 'cyan': mat('cyan data glow','#00cfff',0,0.18,'#00d8ff',4.5),
 'orange': mat('orange sky plastic','#f05a18',0,0.38,'#ff5a18',0.25),
 'red': mat('red temple','#c8281f',0,0.32),
 'green': mat('neon jungle green','#0c8d25',0,0.45,'#35ff6a',0.25),
 'purple': mat('deep purple','#34238c',0,0.25,'#7a35ff',0.45),
 'gold': mat('aged gold','#d6a536',1,0.2),
 'snow': mat('blue snow','#dff6ff',0,0.42),
 'pink': mat('candy pink','#ff7ab8',0,0.2,'#ff4fd8',0.45),
 'mint': mat('candy mint','#7dffd1',0,0.18,'#5dffb4',0.5),
 'sand': mat('orange sand','#d97a22',0,0.55),
 'checker': checker_mat('procedural checker'),
}

def add_obj(collection, obj):
    # Object already linked to scene collection; also link to collection.
    try: collection.objects.link(obj)
    except RuntimeError: pass
    return obj

def cube(col, name, loc, scale, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o=bpy.context.object; o.name=name; o.scale=scale; o.data.materials.append(material); return add_obj(col,o)

def sphere(col, name, loc, radius, material, segments=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=max(12,segments//2), radius=radius, location=loc); o=bpy.context.object; o.name=name; o.data.materials.append(material); return add_obj(col,o)

def ico(col, name, loc, radius, material, subdivisions=2):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=radius, location=loc); o=bpy.context.object; o.name=name; o.data.materials.append(material); return add_obj(col,o)

def torus(col, name, loc, major, minor, material, rot=(0,0,0), seg=96):
    bpy.ops.mesh.primitive_torus_add(major_segments=seg, minor_segments=12, major_radius=major, minor_radius=minor, location=loc)
    o=bpy.context.object; o.name=name; o.rotation_euler=[math.radians(v) for v in rot]; o.data.materials.append(material); return add_obj(col,o)

def cyl(col, name, loc, radius, depth, material, vertices=32, rot=(0,0,0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    o=bpy.context.object; o.name=name; o.rotation_euler=[math.radians(v) for v in rot]; o.data.materials.append(material); return add_obj(col,o)

def cone(col, name, loc, r1, r2, depth, material, vertices=32, rot=(0,0,0)):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=r1, radius2=r2, depth=depth, location=loc)
    o=bpy.context.object; o.name=name; o.rotation_euler=[math.radians(v) for v in rot]; o.data.materials.append(material); return add_obj(col,o)

def plane(col, name, loc, scale, material):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc); o=bpy.context.object; o.name=name; o.scale=scale; o.data.materials.append(material); return add_obj(col,o)

def curve(col, name, pts, material, bevel=0.04):
    cu=bpy.data.curves.new(name, 'CURVE'); cu.dimensions='3D'; cu.resolution_u=8; cu.bevel_depth=bevel; cu.bevel_resolution=3
    spl=cu.splines.new('POLY'); spl.points.add(len(pts)-1)
    for p,co in zip(spl.points, pts): p.co=(co[0],co[1],co[2],1)
    o=bpy.data.objects.new(name, cu); bpy.context.collection.objects.link(o); o.data.materials.append(material); return add_obj(col,o)

def look_at(obj, target):
    d=Vector(target)-obj.location; obj.rotation_euler=d.to_track_quat('-Z','Y').to_euler()

def key_camera(cam, t, loc, target, lens=28):
    cam.location=loc; cam.data.lens=lens; look_at(cam,target)
    f=frame(t); cam.keyframe_insert('location', frame=f); cam.keyframe_insert('rotation_euler', frame=f); cam.data.keyframe_insert('lens', frame=f)

def animate_spin(o, start=1, end=TOTAL, axis='Z', turns=1):
    o.keyframe_insert('rotation_euler', frame=start)
    idx={'X':0,'Y':1,'Z':2}[axis]
    o.rotation_euler[idx]+=math.tau*turns
    o.keyframe_insert('rotation_euler', frame=end)
    if o.animation_data and o.animation_data.action:
        for fc in o.animation_data.action.fcurves:
            for kp in fc.keyframe_points: kp.interpolation='LINEAR'

def hide_key(o, f, hidden):
    o.hide_render=hidden; o.hide_viewport=hidden
    o.keyframe_insert('hide_render', frame=f); o.keyframe_insert('hide_viewport', frame=f)

def visible_between(objs, t0, t1):
    a=max(1,frame(t0)); b=min(TOTAL,frame(t1))
    for o in objs:
        o['show_start'] = a
        o['show_end'] = b
        o.hide_render = True
        o.hide_viewport = True

def update_visibility(scene):
    f = scene.frame_current
    visible = 0
    for o in bpy.data.objects:
        if 'show_start' in o and 'show_end' in o:
            hidden = not (int(o['show_start']) <= f <= int(o['show_end']))
            o.hide_render = hidden
            o.hide_viewport = hidden
            if not hidden:
                visible += 1
    if f in {1, frame(12), frame(27), frame(57), frame(87), frame(105)}:
        print(f'[surreal-dnb] frame {f} visible procedural objects: {visible}')

# setup
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
scene=bpy.context.scene; scene.frame_start=1; scene.frame_end=TOTAL; scene.frame_set(1)
scene.render.resolution_x=WIDTH; scene.render.resolution_y=HEIGHT; scene.render.fps=FPS
scene.render.engine='CYCLES'; scene.cycles.samples=SAMPLES; scene.cycles.preview_samples=min(SAMPLES,32); scene.cycles.use_denoising=True; scene.cycles.max_bounces=5; scene.cycles.diffuse_bounces=2; scene.cycles.glossy_bounces=3; scene.cycles.transparent_max_bounces=4
try:
    scene.cycles.use_persistent_data = True
    print('[surreal-dnb] Cycles persistent data enabled')
except Exception as exc:
    print('[surreal-dnb] persistent data unavailable:', exc)
scene.render.image_settings.file_format='PNG'; scene.render.filepath=str(FRAMES_DIR/'frame_'); scene.render.use_overwrite=False; scene.render.use_placeholder=True
scene.view_settings.view_transform='Filmic'; scene.view_settings.look='High Contrast'; scene.view_settings.exposure=0; scene.view_settings.gamma=1
world=bpy.context.scene.world or bpy.data.worlds.new('World'); bpy.context.scene.world=world; world.color=(0.005,0.006,0.014)

# Render device setup
print(f'[surreal-dnb] Blender {bpy.app.version_string}')
if DEVICE == 'CPU':
    scene.cycles.device='CPU'
    print('[surreal-dnb] Cycles using CPU by request')
else:
    prefs=bpy.context.preferences.addons['cycles'].preferences
    selected=False
    choices = [DEVICE] if DEVICE in ['CUDA','OPTIX'] else ['OPTIX','CUDA']
    for typ in choices:
        try:
            prefs.compute_device_type=typ
            if hasattr(prefs,'refresh_devices'): prefs.refresh_devices()
            else: prefs.get_devices()
        except Exception as e:
            print('[surreal-dnb]', typ, 'unavailable', e); continue
        print('[surreal-dnb] compute_device_type', typ)
        for d in prefs.devices:
            d.use=(getattr(d,'type','')!='CPU')
            print('[surreal-dnb] device', d.name, d.type, 'use=', d.use)
        if any(getattr(d,'use',False) and getattr(d,'type','')!='CPU' for d in prefs.devices):
            selected=True; break
    if not selected: raise SystemExit('[surreal-dnb] ERROR: no GPU Cycles device selected')
    scene.cycles.device='GPU'

# lights/camera
cam_data=bpy.data.cameras.new('Camera'); cam=bpy.data.objects.new('Camera', cam_data); bpy.context.collection.objects.link(cam); scene.camera=cam
bpy.ops.object.light_add(type='AREA', location=(0,-4,8)); key=bpy.context.object; key.name='huge softbox'; key.data.energy=420; key.data.size=7
bpy.ops.object.light_add(type='POINT', location=(0,0,2)); pulse=bpy.context.object; pulse.name='beat pulse core'; pulse.data.energy=120; pulse.data.color=(0.2,0.7,1.0)

collections=[]; objects_by_scene=[]
for _,_,name in SCENES:
    c=bpy.data.collections.new(name); bpy.context.scene.collection.children.link(c); collections.append(c); objects_by_scene.append([])

def add_scene(i,o): objects_by_scene[i].append(o); return o

# 1 tunnel
c=collections[0]
for k in range(34):
    z=-k*1.25
    r=1.5+0.13*math.sin(k*.8)
    o=torus(c,f'tunnel ring {k}',(0,0,z),r,0.018,M['cyan'],rot=(0,0,k*11),seg=72); add_scene(0,o); animate_spin(o,frame(0),frame(12),'Z',1.5)
    if k%3==0:
        p=plane(c,f'data pane {k}',(math.sin(k)*0.95, math.cos(k)*0.95, z-0.3),(0.32,0.02,0.18),M['blue']); p.rotation_euler=(math.radians(90),0,k); add_scene(0,p)
for k in range(8): add_scene(0,sphere(c,f'black seed {k}',(math.sin(k)*.8,math.cos(k*1.7)*.8,-3-k*3),0.18+0.05*(k%3),M['chrome']))

# 2 temple
c=collections[1]; add_scene(1,plane(c,'black mirror floor',(0,0,-.04),(10,10,1),M['blackglass']))
for x in [-3,-1.5,0,1.5,3]:
    for y in [-1.6,1.2]:
        add_scene(1,cyl(c,'gold neck',(x,y,1.2),0.18,2.5,M['gold']))
        add_scene(1,sphere(c,'teal mask',(x,y,2.55),0.34,M['chrome'],24))
        add_scene(1,torus(c,'collar',(x,y,1.0),0.35,0.045,M['purple'],rot=(90,0,0),seg=48))
for k in range(4):
    o=torus(c,f'portal ring {k}',(0,1.8,1.9),1.0+k*.18,0.035,M['cyan'],rot=(90,0,k*22)); add_scene(1,o); animate_spin(o,frame(12),frame(27),'Z',1+k*.25)

# 3 jungle
c=collections[2]; add_scene(2,plane(c,'blue water',(0,0,-.08),(12,8,1),M['blue'])); add_scene(2,plane(c,'green island',(0,0,0),(9,5,1),M['green']))
for k in range(24):
    x=(k%8-3.5)*1.05; y=(k//8-1)*1.25+0.2*math.sin(k)
    add_scene(2,cyl(c,'red trunk',(x,y,.45),.055,.9,M['red']))
    crown=ico(c,'spiky crown',(x,y,1.05),.36,M['green'],2); add_scene(2,crown); animate_spin(crown,frame(27),frame(42),'Z',0.5)
for k in range(5): add_scene(2,sphere(c,'jungle chrome orb',(math.sin(k)*2.2, -1+k*.65, .55+k*.08),.28,M['chrome']))

# 4 desert
c=collections[3]; add_scene(3,plane(c,'orange dunes',(0,0,0),(14,8,1),M['sand']))
for k in range(10): add_scene(3,cone(c,'black obelisk',(-5+k*1.1, math.sin(k)*1.5, .95),.26,.05,1.9+0.4*(k%3),M['blackglass'],vertices=5,rot=(0,0,k*13)))
for k in range(7): add_scene(3,curve(c,'bone cable',[(-5+k*1.5,-1.8,.25),(-4+k*1.5,-.5,.65),(-3.5+k*1.5,1.6,.22)],M['gold'],.035))
for k in range(5): add_scene(3,sphere(c,'mirage pearl',(-3+k*1.5,0.5*math.sin(k),1.1),.42,M['chrome']))

# 5 checker gallery
c=collections[4]; add_scene(4,plane(c,'checker floor',(0,0,0),(12,8,1),M['checker']))
for k in range(7):
    x=-4.5+k*1.5
    add_scene(4,cyl(c,'lamp pole',(x,-1.8,1.2),.035,2.4,M['blackglass']))
    add_scene(4,sphere(c,'warm bulb',(x,-1.8,2.5),.18,M['orange']))
    o=torus(c,'ceiling loop',(x*.25,0.4,2.9),.8,.035,M['chrome'],rot=(90,0,k*23)); add_scene(4,o); animate_spin(o,frame(57),frame(72),'Z',1)
for k in range(6): add_scene(4,sphere(c,'gallery bubble',(-2.8+k*1.1,.5+math.sin(k),.7),.33,M['chrome']))

# 6 snow candy
c=collections[5]; add_scene(5,plane(c,'snow field',(0,0,0),(11,7,1),M['snow']))
for k in range(18): add_scene(5,cone(c,'snow mountain',(-5+k*.6,2.2+0.2*math.sin(k),.45),.35,.0,.9+0.6*((k*7)%5)/5,M['snow'],vertices=5))
for k in range(8): add_scene(5,cyl(c,'candy pillar',(-3.5+k, -0.5+0.45*math.sin(k), .9),.12,1.8,M['pink' if k%2 else 'mint']))
add_scene(5,torus(c,'halo sun',(0,1.2,2.1),.75,.09,M['blue'],rot=(90,0,0))); add_scene(5,sphere(c,'glowing sun',(0,1.2,2.1),.38,M['orange']))

# 7 collision
c=collections[6]; add_scene(6,plane(c,'collision checker',(0,0,0),(12,8,1),M['checker']))
for k in range(18):
    o=torus(c,'collision ring',(math.sin(k)*3, math.cos(k*1.4)*2, .8+0.08*k),.45+.02*k,.025,M['cyan' if k%2 else 'pink'],rot=(90,k*17,k*23),seg=48); add_scene(6,o); animate_spin(o,frame(87),frame(105),'Z',2)
for k in range(16): add_scene(6,curve(c,'green vine',[(math.sin(k)*4,-2,.15),(math.sin(k*.7)*2,0,1.0),(math.cos(k)*4,2,.25)],M['green'],.025))
for k in range(8): add_scene(6,cone(c,'rising shard',(-4+k*1.1, math.sin(k*2), .9),.22,.02,1.8,M['blackglass'],vertices=5))

# 8 ascension
c=collections[7]; add_scene(7,plane(c,'final mirror',(0,0,0),(12,8,1),M['blackglass']))
for k in range(10):
    o=torus(c,'ascension ring',(0,0,0.7+k*.22),.7+k*.16,.025,M['cyan' if k%2 else 'pink'],rot=(90,0,k*18),seg=72); add_scene(7,o); animate_spin(o,frame(105),frame(120),'Z',1.8)
for k in range(9): add_scene(7,sphere(c,'aligned chrome',((k-4)*.42,0,1.25+0.1*math.sin(k)),.18,M['chrome']))
add_scene(7,sphere(c,'portal white',(0,0,2.6),.52,mat('final white','#ffffff',0,0.05,'#e9ffff',7)))

# visibility + camera
for idx, (t0,t1,_) in enumerate(SCENES): visible_between(objects_by_scene[idx],t0,t1)
bpy.app.handlers.frame_change_pre.append(update_visibility)
update_visibility(scene)
key_camera(cam,0,(0,0,2.2),(0,0,-14),22); key_camera(cam,12,(0,0,-29),(0,0,-36),18)
key_camera(cam,12.1,(-4,-5,2.1),(0,1.4,1.6),28); key_camera(cam,27,(3.8,-2.8,3.2),(0,1.3,1.9),35)
key_camera(cam,27.1,(-4.5,-3,1.4),(2,1,0.8),26); key_camera(cam,42,(4,2.6,1.9),(0,0,0.8),30)
key_camera(cam,42.1,(-5,-2.4,.8),(2,.3,.8),24); key_camera(cam,57,(5,-1.6,1.3),(0,0,1),28)
key_camera(cam,57.1,(-4,-4,1.2),(0,0,1.2),22); key_camera(cam,72,(4,2.3,1.6),(0,0,1.7),28)
key_camera(cam,72.1,(-3.6,-3,1.4),(0,1,1.6),35); key_camera(cam,87,(3,2.8,2.0),(0,0,1.8),32)
key_camera(cam,87.1,(-5,-3,1.1),(2,0,1.1),20); key_camera(cam,105,(5,2.5,2.5),(0,0,1.6),24)
key_camera(cam,105.1,(0,-5,1.2),(0,0,1.7),28); key_camera(cam,120,(0,-1.6,4.2),(0,0,2.4),38)
if cam.animation_data and cam.animation_data.action:
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points: kp.interpolation='BEZIER'

bpy.ops.wm.save_as_mainfile(filepath=str(OUT_DIR/'surreal-jungle-dnb-720p.blend'))
print('[surreal-dnb] rendering frames to', FRAMES_DIR)
bpy.ops.render.render(animation=True)
