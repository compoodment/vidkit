#!/usr/bin/env python3
"""Surreal CG DnB 20s v2 Blender render.

Run inside Blender:
  blender -b --python render_scene.py -- <out_dir>

Design constraints:
- no frame-change handlers
- no visibility keyframing/churn
- linked duplicates for repeated meshes
- explicit Cycles GPU device selection
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector

FPS = int(os.environ.get("VIDKIT_FPS", "24"))
DURATION = float(os.environ.get("VIDKIT_DURATION", "20"))
WIDTH = int(os.environ.get("VIDKIT_WIDTH", "1280"))
HEIGHT = int(os.environ.get("VIDKIT_HEIGHT", "720"))
SAMPLES = int(os.environ.get("VIDKIT_SAMPLES", "96"))
DEVICE = os.environ.get("VIDKIT_CYCLES_DEVICE", "CUDA").upper()
ALLOW_CPU = os.environ.get("VIDKIT_ALLOW_CPU", "0") == "1"
BENCHMARK_FRAMES = int(os.environ.get("VIDKIT_BENCHMARK_FRAMES", "48"))
MODE = os.environ.get("VIDKIT_RENDER_MODE", "full").lower()
OUT_DIR = Path(sys.argv[-1]) if len(sys.argv) > 1 and not sys.argv[-1].startswith("-") else Path("outputs/surreal-cg-dnb-20s-v2")
FRAMES_DIR = OUT_DIR / ("benchmark-frames" if MODE == "benchmark" else "frames")
FRAMES_DIR.mkdir(parents=True, exist_ok=True)
TOTAL = int(round(FPS * DURATION))


def log(*parts):
    print("[surreal-v2]", *parts, flush=True)


def hex_rgba(value, alpha=1.0):
    s = str(value).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return (int(s[0:2], 16) / 255, int(s[2:4], 16) / 255, int(s[4:6], 16) / 255, alpha)


def frame(t):
    return int(round(t * FPS)) + 1


# ---------------------------------------------------------------------------
# Scene setup / GPU selection

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = min(BENCHMARK_FRAMES, TOTAL) if MODE == "benchmark" else TOTAL
scene.frame_set(1)
scene.render.engine = "CYCLES"
scene.cycles.samples = SAMPLES if MODE != "benchmark" else min(SAMPLES, int(os.environ.get("VIDKIT_BENCHMARK_SAMPLES", "48")))
scene.cycles.preview_samples = 16
scene.cycles.use_persistent_data = True
scene.cycles.max_bounces = 7
scene.cycles.diffuse_bounces = 2
scene.cycles.glossy_bounces = 4
scene.cycles.transparent_max_bounces = 4
scene.cycles.transmission_bounces = 4
try:
    scene.cycles.denoising_use_gpu = True
except Exception:
    pass
try:
    scene.cycles.denoiser = "OPTIX"
except Exception:
    pass
scene.render.resolution_x = WIDTH
scene.render.resolution_y = HEIGHT
scene.render.fps = FPS
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(FRAMES_DIR / "frame_")
scene.view_settings.view_transform = "Filmic"
scene.view_settings.look = "Medium High Contrast"
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0

# World: orange/purple dusk, close to the references but not image-copied.
world = scene.world or bpy.data.worlds.new("World")
scene.world = world
world.color = (1.0, 0.42, 0.08)


def configure_cycles_device():
    prefs = bpy.context.preferences.addons.get("cycles")
    if not prefs:
        if ALLOW_CPU:
            log("Cycles addon prefs unavailable; CPU allowed for smoke test")
            scene.cycles.device = "CPU"
            return
        raise SystemExit("Cycles addon preferences unavailable")
    cprefs = prefs.preferences
    requested = DEVICE
    if requested == "GPU":
        requested = "CUDA"
    if requested not in {"CUDA", "OPTIX", "HIP", "METAL", "ONEAPI", "AUTO", "CPU"}:
        raise SystemExit(f"Unsupported VIDKIT_CYCLES_DEVICE={DEVICE!r}")
    if requested == "CPU":
        if not ALLOW_CPU:
            raise SystemExit("CPU render requested but VIDKIT_ALLOW_CPU=1 was not set")
        scene.cycles.device = "CPU"
        log("Using CPU render for local smoke test")
        return

    order = [requested] if requested != "AUTO" else ["OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"]
    selected = None
    devices = []
    for backend in order:
        try:
            cprefs.compute_device_type = backend
            cprefs.get_devices()
            devices = list(cprefs.devices)
            gpu_devices = [d for d in devices if getattr(d, "type", "") != "CPU"]
            if gpu_devices:
                selected = backend
                break
        except Exception as exc:
            log("backend probe failed", backend, exc)

    log("Blender", bpy.app.version_string)
    log("requested device", DEVICE, "selected", selected)
    if not selected:
        for d in devices:
            log("device", getattr(d, "name", "?"), getattr(d, "type", "?"), "use=", getattr(d, "use", None))
        if ALLOW_CPU:
            log("No GPU available; falling back to CPU because VIDKIT_ALLOW_CPU=1")
            scene.cycles.device = "CPU"
            return
        raise SystemExit(f"No usable Cycles GPU device for request {DEVICE}")

    scene.cycles.device = "GPU"
    cprefs.compute_device_type = selected
    cprefs.get_devices()
    for d in cprefs.devices:
        is_cpu = getattr(d, "type", "") == "CPU"
        d.use = not is_cpu
        log("device", getattr(d, "name", "?"), getattr(d, "type", "?"), "use=", d.use)
    log("Cycles using GPU via", selected)


configure_cycles_device()


# ---------------------------------------------------------------------------
# Materials


def make_mat(name, base, metallic=0.0, roughness=0.35, emission=None, strength=0.0, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = hex_rgba(base, alpha)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = hex_rgba(base, alpha)
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        if emission:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = hex_rgba(emission)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = strength
    if alpha < 1.0:
        mat.blend_method = "BLEND"
        mat.use_screen_refraction = True
    return mat


def noise_mat(name, color1, color2, scale=18, metallic=0.0, roughness=0.35):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 9
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = hex_rgba(color1)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = hex_rgba(color2)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


M = {
    "sand": noise_mat("orange whipped sand", "#c66317", "#ffb12d", 28, 0, 0.65),
    "chocolate": make_mat("dark chocolate gloss", "#2c160d", 0, 0.18),
    "candy_red": make_mat("hard candy red", "#b40018", 0, 0.08, "#ff2038", 0.25),
    "candy_mint": make_mat("striped mint", "#7dffd8", 0, 0.18, "#61ffbc", 0.35),
    "candy_cream": make_mat("candy cream", "#fff0b8", 0, 0.22),
    "chrome": make_mat("mirror chrome", "#e8fbff", 1.0, 0.03),
    "glass": make_mat("faint violet glass", "#b47cff", 0.0, 0.02, "#a55cff", 0.1, 0.38),
    "temple_red": make_mat("temple red clay", "#d23a26", 0.0, 0.32, "#ff392a", 0.12),
    "temple_blue": make_mat("temple cobalt", "#1833c9", 0.0, 0.22),
    "mask_teal": make_mat("oxidized teal mask", "#38b8a0", 0.2, 0.18, "#44ffe0", 0.22),
    "gold": make_mat("old gold", "#d4a336", 1.0, 0.16),
    "blackrock": noise_mat("black obsidian rock", "#050407", "#2b1815", 20, 0.2, 0.2),
    "green": noise_mat("acid jungle canopy", "#064c16", "#36ff52", 34, 0, 0.45),
    "trunk": make_mat("red alien trunk", "#8d1e16", 0, 0.38),
    "water": make_mat("deep blue water glow", "#0622a0", 0.0, 0.08, "#003cff", 0.45),
    "purple": make_mat("deep violet plastic", "#3b1ca2", 0.0, 0.18, "#6432ff", 0.32),
    "orange_glow": make_mat("orange glow", "#ff7b1a", 0.0, 0.3, "#ff5a00", 1.2),
}


# ---------------------------------------------------------------------------
# Helpers


def shade(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    try:
        bpy.ops.object.shade_smooth()
    except Exception:
        pass
    obj.select_set(False)
    return obj


def add_cube(name, loc, scale, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    return obj


def add_plane(name, loc, scale, material):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    if material:
        obj.data.materials.append(material)
    return obj


def add_uv(name, loc, scale, material, segments=48, rings=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    if material:
        obj.data.materials.append(material)
    return shade(obj)


def add_cyl(name, loc, radius, depth, material, vertices=48, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    if material:
        obj.data.materials.append(material)
    return shade(obj)


def add_cone(name, loc, r1, r2, depth, material, vertices=48, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=r1, radius2=r2, depth=depth, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    if material:
        obj.data.materials.append(material)
    return shade(obj)


def add_torus(name, loc, major, minor, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=72, minor_segments=12, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    if material:
        obj.data.materials.append(material)
    return shade(obj)


def linked(obj, name, loc, rot=None, scale=None):
    dup = obj.copy()
    dup.data = obj.data
    dup.animation_data_clear()
    dup.name = name
    dup.location = loc
    if rot is not None:
        dup.rotation_euler = rot
    if scale is not None:
        dup.scale = scale
    bpy.context.collection.objects.link(dup)
    return dup


def add_curve(name, points, material, bevel=0.08):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 18
    curve.bevel_depth = bevel
    curve.bevel_resolution = 5
    spl = curve.splines.new("BEZIER")
    spl.bezier_points.add(len(points) - 1)
    for p, co in zip(spl.bezier_points, points):
        p.co = Vector(co)
        p.handle_left_type = p.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    if material:
        curve.materials.append(material)
    return obj


def add_manta(name, loc, scale, material, rot=(0, 0, 0)):
    mesh = bpy.data.meshes.new(name + "Mesh")
    verts = [(-1.6, 0, 0), (-0.25, 0.55, 0.08), (0, 0, -0.1), (0.25, 0.55, 0.08), (1.6, 0, 0), (0, -0.42, 0.06)]
    faces = [(0, 1, 2), (2, 3, 4), (0, 2, 5), (2, 4, 5)]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.scale = scale
    obj.rotation_euler = rot
    bpy.context.collection.objects.link(obj)
    if material:
        mesh.materials.append(material)
    return obj


def key_obj(obj, t0, t1, rot0=None, rot1=None, loc0=None, loc1=None):
    if loc0 is not None:
        obj.location = loc0
        obj.keyframe_insert("location", frame=frame(t0))
    if rot0 is not None:
        obj.rotation_euler = rot0
        obj.keyframe_insert("rotation_euler", frame=frame(t0))
    if loc1 is not None:
        obj.location = loc1
        obj.keyframe_insert("location", frame=frame(t1))
    if rot1 is not None:
        obj.rotation_euler = rot1
        obj.keyframe_insert("rotation_euler", frame=frame(t1))
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "SINE" if False else "BEZIER"


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


# ---------------------------------------------------------------------------
# Set pieces. Spatially separated zones, all active/static; camera cuts between them.

# Global ground slabs
add_plane("endless orange desert", (80, 0, -0.03), (260, 90, 1), M["sand"])

# 1. Candy desert shrine / chrome jellyfish tower
base = add_cube("chocolate grid tile base", (0, 0, 0.03), (14, 8, 0.12), M["chocolate"])
for x in range(-6, 7, 2):
    add_cube("raised chocolate grid x", (x, 0, 0.16), (0.08, 8.1, 0.08), M["gold"])
for y in range(-4, 5, 2):
    add_cube("raised chocolate grid y", (0, y, 0.17), (14.1, 0.08, 0.08), M["gold"])

lolli_stem = add_cyl("linked lollipop stem source", (-5.8, -3.0, 0.8), 0.035, 1.4, M["candy_cream"], 16)
lolli_head = add_uv("linked red lollipop source", (-5.8, -3.0, 1.55), (0.34, 0.34, 0.34), M["candy_red"], 32, 16)
for i, (x, y, h) in enumerate([(-4, -3.5, 1.2), (-1.7, -3.7, 1.6), (2.4, -3.55, 1.25), (5.2, -3.2, 1.5), (-5.1, 3.1, 1.4), (0.5, 3.55, 1.2), (5.5, 2.8, 1.75)]):
    linked(lolli_stem, f"lollipop stem {i}", (x, y, h / 2), scale=(1, 1, h / 1.4))
    linked(lolli_head, f"lollipop head {i}", (x, y, h + 0.22))

# Jellyfish tower: candy tentacles + chrome cap.
for i in range(9):
    ang = i * math.tau / 9
    r = 0.55 + 0.25 * (i % 2)
    x = 2.8 + math.cos(ang) * r
    y = 0.7 + math.sin(ang) * r
    add_curve(f"striped jelly tentacle {i}", [(x, y, 0.25), (x * 0.98, y * 0.98, 1.8), (2.8 + math.cos(ang + 0.6) * 0.35, 0.7 + math.sin(ang + 0.6) * 0.35, 3.5)], M["candy_mint" if i % 2 else "candy_cream"], 0.055)
add_uv("chrome jellyfish dome", (2.8, 0.7, 3.95), (1.25, 1.25, 0.62), M["chrome"], 64, 24)
add_torus("red-white shrine ring", (2.8, 0.7, 2.05), 0.92, 0.08, M["candy_red"])

# 2. Porray temple: columns with face masks and central orb.
OX = 45
add_plane("temple reflective floor", (OX, 0, 0), (13, 9, 1), M["purple"])
add_uv("porray glass orb", (OX, 0, 2.2), (1.25, 1.25, 1.25), M["glass"], 64, 32)
add_torus("orb halo low", (OX, 0, 2.2), 1.65, 0.035, M["gold"], (math.pi / 2, 0, 0))
add_torus("orb halo high", (OX, 0, 2.2), 1.9, 0.035, M["temple_blue"], (0.72, 0.2, 0.4))
col_source = add_cyl("linked temple column source", (OX - 5, -3, 2), 0.32, 4.0, M["temple_blue"], 48)
ring_source = add_torus("linked column torus source", (OX - 5, -3, 0.8), 0.34, 0.08, M["gold"])
mask_source = add_uv("linked teal face mask source", (OX - 5, -3.34, 2.35), (0.28, 0.09, 0.46), M["mask_teal"], 32, 16)
for i, x in enumerate([-5, -2.5, 2.5, 5]):
    for j, y in enumerate([-3.2, 3.2]):
        name = f"face column {i}-{j}"
        linked(col_source, name, (OX + x, y, 2.0))
        linked(ring_source, name + " lower gold ring", (OX + x, y, 0.8))
        linked(ring_source, name + " upper gold ring", (OX + x, y, 3.2))
        front = linked(mask_source, name + " mask front", (OX + x, y - (0.36 if y < 0 else -0.36), 2.35), rot=(0, 0, 0 if y < 0 else math.pi))
        # small nose spike to make masks read as faces
        add_cone(name + " mask nose", (OX + x, y - (0.48 if y < 0 else -0.48), 2.35), 0.08, 0.0, 0.22, M["mask_teal"], 16, (math.pi / 2 if y < 0 else -math.pi / 2, 0, 0))
add_cyl("red temple ceiling disk", (OX, 0, 4.3), 5.6, 0.28, M["temple_red"], 96)

# 3. Desert cable bones / monolith field.
OX = 90
for i, y in enumerate([-2.4, -1.0, 0.7, 2.2]):
    add_curve(f"chrome rib cable {i}", [(OX - 7, y, 0.25), (OX - 3, y + 0.8 * math.sin(i), 1.2), (OX + 2, y - 0.7, 0.55), (OX + 7, y + 0.35, 0.25)], M["chrome"], 0.115)
for i, x in enumerate([-5.8, -1.8, 3.8, 7.0]):
    add_cone(f"black desert monolith {i}", (OX + x, 2.8 - i * 1.3, 1.8), 0.65, 0.16, 3.6 + i * 0.7, M["blackrock"], 5, (0.08 * i, 0.2, 0.1 * i))
for i in range(16):
    x = OX - 6 + i * 0.8
    y = -2.9 + math.sin(i * 1.9) * 0.45
    add_cone(f"small desert shard {i}", (x, y, 0.25), 0.18, 0.02, 0.55 + (i % 3) * 0.15, M["blackrock"], 5)

# 4. Green sky jungle with manta shapes.
OX = 135
add_plane("blue jungle wetlands", (OX, 0, 0.012), (15, 8.5, 1), M["water"])
canopy_src = add_uv("linked bulb canopy source", (OX - 6, -2, 1.3), (0.62, 0.62, 0.48), M["green"], 24, 12)
trunk_src = add_cyl("linked red trunk source", (OX - 6, -2, 0.55), 0.07, 1.1, M["trunk"], 12)
for i in range(32):
    x = OX - 7 + (i % 8) * 2.0 + math.sin(i) * 0.25
    y = -3.3 + (i // 8) * 2.1 + math.cos(i * 1.7) * 0.25
    h = 0.9 + (i % 5) * 0.12
    linked(trunk_src, f"jungle trunk {i}", (x, y, h / 2), scale=(1, 1, h / 1.1))
    linked(canopy_src, f"jungle bulb canopy {i}", (x, y, h + 0.55), scale=(0.8 + (i % 3) * 0.18, 0.8 + (i % 4) * 0.11, 0.6))
for i in range(5):
    manta = add_manta(f"distant manta {i}", (OX - 5 + i * 2.8, -4.2 + i * 1.6, 3.0 + i * 0.35), (0.9 + i * 0.1, 0.9 + i * 0.1, 0.9), M["blackrock"], (0.1, 0.0, 0.35 + i * 0.2))
    key_obj(manta, 12.0, 16.0, loc0=manta.location.copy(), loc1=(manta.location.x + 2.5, manta.location.y + 0.3, manta.location.z + 0.2))

# 5. Chrome egg canyon finale.
OX = 180
add_plane("blue canyon river", (OX, 0, -0.02), (15, 6, 1), M["water"])
for side in [-1, 1]:
    for i in range(9):
        add_cone(f"jagged canyon wall {side}-{i}", (OX - 7 + i * 1.75, side * (3.8 + 0.4 * math.sin(i)), 2.0), 0.75 + 0.2 * (i % 3), 0.18, 4.0 + 1.3 * ((i + 1) % 3), M["blackrock"], 5, (0.15 * side, 0.25 * math.sin(i), 0.2 * i))
egg_src = add_uv("linked chrome egg source", (OX - 4, -0.3, 1.5), (0.75, 0.75, 1.05), M["chrome"], 64, 32)
for i, (x, y, z, s) in enumerate([(-4.8, -1.0, 1.0, 0.65), (-2.2, 0.9, 1.8, 1.0), (0.4, -0.8, 2.5, 0.8), (2.9, 1.1, 3.3, 1.15), (5.2, -0.2, 4.3, 0.7)]):
    o = linked(egg_src, f"floating chrome egg {i}", (OX + x, y, z), rot=(0.2 * i, 0.1, 0.4 * i), scale=(s * 0.75, s * 0.75, s * 1.05))
    key_obj(o, 16.0, 20.0, rot0=o.rotation_euler.copy(), rot1=(o.rotation_euler.x + 0.45, o.rotation_euler.y + 0.2, o.rotation_euler.z + 1.2))

# Lighting: broad emissive area lights and colored accents.
bpy.ops.object.light_add(type="SUN", location=(0, 0, 12))
sun = bpy.context.object
sun.name = "molten orange sun"
sun.data.energy = 1.5
sun.rotation_euler = (math.radians(38), 0, math.radians(40))
for i, (x, y, z, color, energy) in enumerate([
    (2, -3, 5, (1.0, 0.55, 0.22), 450),
    (45, -4, 5, (0.85, 0.18, 1.0), 500),
    (90, -2, 4, (1.0, 0.42, 0.16), 380),
    (135, -5, 6, (0.2, 0.95, 0.35), 500),
    (180, -3, 6, (0.1, 0.38, 1.0), 650),
]):
    bpy.ops.object.light_add(type="AREA", location=(x, y, z))
    l = bpy.context.object
    l.name = f"shot colored softbox {i}"
    l.data.energy = energy
    l.data.size = 5.5
    l.data.color = color

# Camera animation: each shot has a distinct grammar.
bpy.ops.object.camera_add(location=(-7.2, -4.0, 0.75))
cam = bpy.context.object
scene.camera = cam
cam.data.lens = 24
cam.data.dof.use_dof = True
cam.data.dof.aperture_fstop = 5.6

cam_keys = [
    # candy: low forward dolly
    (0.0, (-7.2, -4.0, 0.75), (2.8, 0.7, 2.7), 22),
    (3.85, (1.2, -1.4, 1.55), (2.8, 0.7, 3.9), 30),
    # temple: crane/roll upward through columns
    (4.0, (45, -6.2, 0.85), (45, 0, 2.1), 24),
    (7.85, (45.8, -1.8, 3.65), (45, 0, 2.45), 34),
    # desert bones: ground skim tracking sideways
    (8.0, (82.3, -3.1, 0.38), (92.0, -1.2, 0.8), 20),
    (11.85, (96.4, -2.0, 0.62), (91.0, 1.7, 1.7), 26),
    # jungle: aerial swoop
    (12.0, (128.0, -6.0, 4.2), (135, 0, 1.1), 20),
    (15.85, (141.0, 2.2, 1.4), (136, 0.4, 1.2), 32),
    # canyon: spiral/ascent rather than pan
    (16.0, (175.0, -3.0, 0.85), (180.2, 0, 2.2), 22),
    (18.0, (181.2, -2.4, 2.9), (180.4, 0.2, 2.8), 26),
    (20.0, (184.5, 1.6, 5.2), (181.4, 0.2, 4.2), 35),
]
for t, loc, target, lens in cam_keys:
    cam.location = loc
    cam.data.lens = lens
    look_at(cam, target)
    cam.keyframe_insert("location", frame=frame(t))
    cam.keyframe_insert("rotation_euler", frame=frame(t))
    cam.data.keyframe_insert("lens", frame=frame(t))

# Make cuts close to instantaneous, but leave in-shot motion smooth.
if cam.animation_data and cam.animation_data.action:
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"

# Animate a few hero forms with ordinary keyframes only.
for obj in [o for o in bpy.data.objects if "chrome jellyfish dome" in o.name or "porray glass orb" in o.name or "red-white shrine ring" in o.name]:
    key_obj(obj, 0.0, 8.0, rot0=(0, 0, 0), rot1=(0, 0, math.tau * 0.35))

# Render.
log("mode", MODE, "frames", scene.frame_start, scene.frame_end, "fps", FPS, "size", WIDTH, HEIGHT, "samples", scene.cycles.samples)
log("frame output", scene.render.filepath)
bpy.ops.render.render(animation=True)
log("render complete", FRAMES_DIR)
