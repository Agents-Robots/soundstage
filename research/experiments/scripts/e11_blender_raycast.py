"""E11: ray casting in Blender for the visibility bake. Needs Blender.

Builds a synthetic city in headless Blender: a grid of building instances (geometry nodes
instancing a few detailed meshes) plus moving cars, and measures per-ray cost of
``scene.ray_cast``, of a BVH over the instances' bounding boxes (the bake's occluders) and of a BVH
over real triangles (built for a subset, extrapolated), and the bake's visibility cost per sample.
"""

import json
import subprocess
import tempfile
from pathlib import Path

from common import REPO, table

BLENDER = r'''
import bpy, json, math, sys, time, resource
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0, {repo!r})
from soundstage.blender import occlusion

GRID, SPACING, LEVELS = {grid}, 30.0, 4
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, 100

# a few building types: subdivided boxes (detail stands in for windows, ledges)
assets = bpy.data.collections.new("Buildings")
for k in range(4):
    bpy.ops.mesh.primitive_cube_add(size=1)
    b = bpy.context.object
    b.name = f"Building{{k}}"
    b.scale = (12 + 4 * k, 12, 20 + 15 * k)
    bpy.ops.object.transform_apply(scale=True)
    mod = b.modifiers.new("detail", "SUBSURF"); mod.subdivision_type = "SIMPLE"; mod.levels = LEVELS
    bpy.ops.object.modifier_apply(modifier="detail")
    for c in list(b.users_collection):
        c.objects.unlink(b)
    assets.objects.link(b)

# grid of points, one building per point: geometry-nodes instances, or objects sharing the meshes
pts = [(x * SPACING, y * SPACING, 0) for x in range(GRID) for y in range(GRID)]
if {objects}:
    types = list(assets.objects)
    for i, pt in enumerate(pts):
        o = bpy.data.objects.new(f"B{{i}}", types[i % 4].data)
        o.location = pt
        scene.collection.objects.link(o)
mesh = bpy.data.meshes.new("plots"); mesh.from_pydata([] if {objects} else pts, [], [])
city = bpy.data.objects.new("City", mesh); scene.collection.objects.link(city)
tree = bpy.data.node_groups.new("city", "GeometryNodeTree")
tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
nin, nout = tree.nodes.new("NodeGroupInput"), tree.nodes.new("NodeGroupOutput")
info = tree.nodes.new("GeometryNodeCollectionInfo")
info.inputs["Collection"].default_value = assets
info.inputs["Separate Children"].default_value = True
info.inputs["Reset Children"].default_value = True
iop = tree.nodes.new("GeometryNodeInstanceOnPoints")
iop.inputs["Pick Instance"].default_value = True
index = tree.nodes.new("GeometryNodeInputIndex")
pick = tree.nodes.new("ShaderNodeMath"); pick.operation = "FLOORED_MODULO"; pick.inputs[1].default_value = 4
tree.links.new(index.outputs[0], pick.inputs[0])
tree.links.new(nin.outputs[0], iop.inputs["Points"]); tree.links.new(info.outputs[0], iop.inputs["Instance"])
tree.links.new(pick.outputs[0], iop.inputs["Instance Index"]); tree.links.new(iop.outputs[0], nout.inputs[0])
city.modifiers.new("GN", "NODES").node_group = tree

# moving cars in the streets
cars = []
for i in range({cars}):
    bpy.ops.mesh.primitive_cube_add(size=1)
    c = bpy.context.object
    c.scale = (4.5, 2, 1.5)
    y = (i % GRID) * SPACING + SPACING / 2
    c.location = (0, y, 1); c.keyframe_insert("location", frame=1)
    c.location = (GRID * SPACING * 0.8, y, 1); c.keyframe_insert("location", frame=100)
    cars.append(c)

dg = bpy.context.evaluated_depsgraph_get()
tris = {{b.name: sum(len(p.vertices) - 2 for p in b.data.polygons) for b in assets.objects}}
by_mesh = {{b.data.name: n for b, n in zip(assets.objects, tris.values())}}
buildings = [(inst.object.original.name, inst.object.original.data.name) for inst in dg.object_instances
             if inst.object.type == "MESH" and inst.object.original.data.name in by_mesh]  # assets are not in the scene
n_inst = len(buildings)
total_tris = sum(by_mesh[m] for _, m in buildings)
tris = {{name: by_mesh[m] for name, m in buildings}}

rng = np.random.default_rng(0)
size = GRID * SPACING
def rays(n):
    a = np.c_[rng.uniform(0, size, n), rng.uniform(0, size, n), np.full(n, 1.7)]
    b = np.c_[rng.uniform(0, size, n), rng.uniform(0, size, n), rng.uniform(1, 30, n)]
    return a, b

out = {{"instances": n_inst, "objects": len(scene.objects), "triangles": total_tris}}
a, b = rays(50)
hits = []
t0 = time.perf_counter()
for i in range(len(a)):
    d = Vector(b[i] - a[i])
    hits.append(scene.ray_cast(dg, Vector(a[i]), d.normalized(), distance=d.length)[0])
out["scene_ray_cast_ms"] = (time.perf_counter() - t0) / len(a) * 1000
out["scene_ray_cast_blocked"] = float(np.mean(hits))
ray_a, ray_b = a, b

t0 = time.perf_counter()
occ = occlusion.Occluders(scene, [1.0, 50.0, 100.0], 2.0, 1.0)
out["boxes_build_s"] = time.perf_counter() - t0
out["boxes"] = occ.counts
occ.update(dg)
out["box_bvh_blocked_same_rays"] = float(occ.blocked(ray_a, ray_b).mean())
a, b = rays(20000)
t0 = time.perf_counter()
blocked = occ.blocked(a, b)
out["box_bvh_us"] = (time.perf_counter() - t0) / len(a) * 1e6
out["blocked_share"] = float(blocked.mean())

# BVH over real triangles for a subset of the instances, extrapolated
dg = bpy.context.evaluated_depsgraph_get()
subset = [(inst.object.original.name, np.array(inst.matrix_world)) for inst in dg.object_instances
          if inst.object.type == "MESH" and inst.object.original.name in tris][:200]  # copies: instances live only while iterating
verts, faces, off = [], [], 0
t0 = time.perf_counter()
for name, m in subset:
    me = bpy.data.objects[name].data
    co = np.array([tuple(v.co) for v in me.vertices]) @ m[:3, :3].T + m[:3, 3]
    verts.append(co); faces += [[i + off for i in p.vertices] for p in me.polygons]; off += len(co)
rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
tree_m = BVHTree.FromPolygons(np.concatenate(verts).tolist(), faces)
sub_tris = sum(len(f) - 2 for f in faces)
out["mesh_bvh_subset"] = {{"instances": len(subset), "triangles": sub_tris,
                          "build_s": time.perf_counter() - t0,
                          "rss_growth_mb": (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - rss0) / 1024}}

# the bake's visibility for 50 sources at one sample
listener = np.array([size / 2, size / 2 + SPACING / 2, 1.7])
sources = np.c_[rng.uniform(0, size, 50), rng.uniform(0, size, 50), np.full(50, 1.0)]
t0 = time.perf_counter()
occ.update(dg)
v = occlusion.visibility(occ, listener, sources, [0.25] * 50, 1.0)
out["visibility_50_sources_ms"] = (time.perf_counter() - t0) * 1000
out["visible_share"] = float(v.mean())
print("E11JSON" + json.dumps(out))
'''


def main() -> None:
    rows = []
    for grid, cars, objects in ((40, 40, False), (100, 100, False), (40, 40, True), (100, 100, True)):
        tmp = Path(tempfile.mkdtemp(prefix="e11_"))
        script = tmp / "city.py"
        script.write_text(BLENDER.format(repo=str(REPO), grid=grid, cars=cars, objects=objects))
        res = subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script)],
                             capture_output=True, text=True, check=True)
        out = json.loads(res.stdout.split("E11JSON", 1)[1].splitlines()[0])
        sub = out["mesh_bvh_subset"]
        per_tri_mb = sub["rss_growth_mb"] / sub["triangles"]
        rows.append([f"{out['instances']} buildings ({'objects' if objects else 'GN instances'}) + {cars} cars",
                     f"{out['triangles'] / 1e6:.0f} M",
                     f"{out['scene_ray_cast_ms']:.1f} ms",
                     f"{out['scene_ray_cast_blocked'] * 100:.0f} / {out['box_bvh_blocked_same_rays'] * 100:.0f} %",
                     f"{out['boxes']['static']} + {out['boxes']['moving']} in {out['boxes_build_s']:.2f} s",
                     f"{out['box_bvh_us']:.1f} µs",
                     f"{sub['build_s'] / sub['triangles'] * out['triangles']:.0f} s, "
                     f"{per_tri_mb * out['triangles'] / 1024:.1f} GB",
                     f"{out['visibility_50_sources_ms']:.0f} ms"])
        print(json.dumps(out))
    print("\nPer ray: scene.ray_cast against a BVH over the instances' oriented bounding boxes; a BVH over the\n"
          "real triangles extrapolated from 200 instances; visibility = one bake sample, 50 sources\n")
    print(table(["scene", "triangles", "scene.ray_cast", "blocked: ray_cast / boxes", "boxes (static + moving)",
                 "box BVH",
                 "triangle BVH (extrapolated)", "visibility"], rows))


if __name__ == "__main__":
    main()
