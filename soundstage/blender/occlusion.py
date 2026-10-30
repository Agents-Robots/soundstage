"""Visibility of sources from the listener (FR-25), from which the engine computes occlusion (FR-47).

Model (research/models/occlusion.md): the fraction of the first Fresnel zone of the direct path
that is open, per frequency band (after Tsingos and Gascuel's Fresnel-ellipsoid visibility). For
each band, points on the zone's equal-area median ring at the path's midpoint (radius
``sqrt(lambda d) / 2 / sqrt(2)``, at least ``occlusion_radius``) are secondary sources; a point is
open when both segments listener -> point -> source are unobstructed. Visibility of a band is the
open share of its points and the direct path. Low frequencies have wide zones and bend around
small obstacles; high frequencies are blocked by them. The path is that of the sound heard at the
sample: from where the source was when it emitted it (retarded by the propagation delay) to the
listener at the sample; moving occluders are where they were when that sound passed them. An
occluder beyond both endpoints (the ground under both) reflects instead of blocking.

Occluders: oriented bounding boxes of the mesh objects and instances that are rendered (of their
connected parts, the mesh islands, when the largest part fills less than half of the box), each
larger than ``occluder_min_size``; an object's custom property ``sfx_occluder`` = False excludes it,
"mesh" uses its real triangles. Meshes whose materials only emit or pass light (fog volumes, light
beams, holograms), text objects and objects that travel with the listener (the camera's vehicle) do
not occlude. Static boxes go into one BVH tree; moving ones into a small tree
rebuilt per sample. A moving instance whose matrix relative to its instancer is the same at every
snapshot (a part of a keyed collection-instance empty) is moved by its instancer's matrix; only the
others are looked up in the depsgraph's instances, a walk over every instance of the scene. A box that contains the listener or the source (an engine inside its car, a
camera inside a cockpit) does not occlude that source's paths.

Runs inside Blender (bpy, mathutils, Blender's numpy).
"""

from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from soundstage.blender import util

BANDS_HZ = (250.0, 1000.0, 4000.0)
POINTS_PER_BAND = 4
PATHS = 1 + len(BANDS_HZ) * POINTS_PER_BAND  # paths per source and sample: the direct path and the ring points
RING_OFFSET_DEG, RING_STEP_DEG = 22.5, 15.0
SPEED_OF_SOUND = 343.0
BOX_FACES = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                      [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
BOX_ORDER = [0, 4, 7, 3, 1, 5, 6, 2]  # Blender bound_box corners -> bottom quad, top quad
CLEARANCE_BU = 1e-3  # a ray continued past an occluder starts this far behind the face it hit
HISTORY = 128  # moving-occluder samples kept for their retarded positions (12.8 s at 10 Hz)
MAX_RECAST = 16  # rays continued past reflecting occluders
SPLIT_FILL = 0.5  # a mesh is split into its parts when its largest part fills less of its box
BY_INSTANCER = True  # moving instances rigid with their instancer: by its matrix (False: depsgraph walk, tests)


def _key(inst) -> tuple:
    if inst.is_instance and inst.parent is not None:
        return (inst.parent.original.name, tuple(inst.persistent_id), inst.object.original.name)
    return (None, (), inst.object.original.name)


def _occluder_mode(inst) -> str | None:
    """None (skip), "box" or "mesh" from the object's or instancing collection's ``sfx_occluder``."""
    orig = inst.object.original
    flag = orig.get("sfx_occluder")
    if flag is None and inst.is_instance and inst.parent is not None:
        coll = inst.parent.original.instance_collection
        flag = coll.get("sfx_occluder") if coll is not None else None
    if flag == "off" or (flag is not None and not isinstance(flag, str) and not flag):  # False, 0
        return None
    return "mesh" if flag == "mesh" else "box"


LIGHT_ONLY_SHADERS = {"EMISSION", "BSDF_TRANSPARENT", "HOLDOUT", "ADD_SHADER", "MIX_SHADER"}


def _light_only(mat) -> bool:
    """A material that only emits or passes light (fog and haze volumes, light beams, glows,
    holograms): nothing sound would bounce off. Glass is not light-only: glass panes block sound."""
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return False
    outputs = [n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL"]
    out = next((n for n in outputs if n.is_active_output), outputs[0] if outputs else None)
    if out is None:
        return False
    surface = out.inputs["Surface"]
    if not surface.is_linked:
        return out.inputs["Volume"].is_linked  # volume only
    shaders, todo, seen = set(), [link.from_node for link in surface.links], set()
    while todo:
        node = todo.pop()
        if node.name in seen:
            continue
        seen.add(node.name)
        if any(o.type == "SHADER" for o in node.outputs):
            shaders.add(node.type)
            todo += [link.from_node for i in node.inputs if i.type == "SHADER" for link in i.links]
    return bool(shaders) and shaders <= LIGHT_ONLY_SHADERS


def _solid(ob, cache: dict) -> bool:
    """Whether a mesh has at least one material slot that is not light-only (or no materials)."""
    key = ob.original.name
    if key not in cache:
        mats = [slot.material for slot in ob.material_slots]
        cache[key] = not mats or not all(_light_only(m) for m in mats)
    return cache[key]


def _corners(lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """The 8 corners of an axis-aligned box, in Blender's ``bound_box`` order."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    return np.array([(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0),
                     (x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)])


def _islands(me) -> tuple[np.ndarray, np.ndarray]:
    """Local box corners (K, 8, 3) of the connected parts of a mesh and their diagonals (K,), largest
    first. A merged mesh (the brackets around a tower, a railing, the buildings of a district in one
    object) becomes one box per part instead of one box full of air."""
    n = len(me.vertices)
    if n == 0:
        return np.zeros((0, 8, 3)), np.zeros(0)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    e = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", e)
    e = e.reshape(-1, 2).astype(np.int64)
    parent = np.arange(n)
    for _ in range(64):  # union-find in rounds: hook the larger root of each edge onto the smaller,
        pu, pv = parent[e[:, 0]], parent[e[:, 1]]  # then jump pointers to full depth (0.1 s for 2 M edges)
        if np.array_equal(pu, pv):
            break
        parent[np.maximum(pu, pv)] = np.minimum(pu, pv)  # duplicate writes: one wins, later rounds do the rest
        while True:
            grand = parent[parent]
            if np.array_equal(grand, parent):
                break
            parent = grand
    _, island = np.unique(parent, return_inverse=True)
    order = np.argsort(island, kind="stable")
    starts = np.concatenate([[0], np.nonzero(np.diff(island[order]))[0] + 1])
    lo = np.minimum.reduceat(co[order], starts, axis=0)
    hi = np.maximum.reduceat(co[order], starts, axis=0)
    # keep the whole box when one part fills most of it (a building with windows, ledges, frames as
    # separate parts): splitting only pays where the box is mostly air
    whole_lo, whole_hi = co.min(axis=0), co.max(axis=0)
    eps = 0.01 * max(float(np.linalg.norm(whole_hi - whole_lo)), 1e-9)
    volume = np.prod(np.maximum(hi - lo, eps), axis=1)
    if volume.max() >= SPLIT_FILL * np.prod(np.maximum(whole_hi - whole_lo, eps)):
        lo, hi = whole_lo[None], whole_hi[None]
    diag = np.linalg.norm(hi - lo, axis=1)
    big = np.argsort(-diag, kind="stable")
    return np.array([_corners(lo[i], hi[i]) for i in big]).reshape(-1, 8, 3), diag[big]


def _snapshot(depsgraph, min_size_bu: float, cache: dict) -> dict:
    """Occluders at the current frame: key -> (matrix, local box corners, mode, evaluated object).
    Box occluders get one entry per mesh island (key ends with the island index)."""
    out = {}
    solid, islands = cache.setdefault("solid", {}), cache.setdefault("islands", {})
    for inst in depsgraph.object_instances:
        ob = inst.object
        if ob.type != "MESH" or ob.original.hide_render or ob.original.type == "FONT":
            continue  # text: a box over lettering closes the gaps between the letters (signs, holograms)
        mode = _occluder_mode(inst)
        if mode is None or (mode == "box" and not _solid(ob, solid)):
            continue
        m = np.array(inst.matrix_world)
        if mode == "mesh":
            parts = np.array([tuple(c) for c in ob.bound_box])[None]
        else:
            name = ob.original.name
            if name not in islands:
                islands[name] = _islands(ob.data)
            parts, diag = islands[name]
            # only the parts that can reach the size at this instance's scale (parts are sorted by size)
            parts = parts[: np.searchsorted(-diag, -min_size_bu / max(np.linalg.norm(m[:3, :3], axis=0).max(), 1e-9),
                                            side="right")]
        key = _key(inst)
        for k, local in enumerate(parts):
            world = local @ m[:3, :3].T + m[:3, 3]
            if np.linalg.norm(world.max(axis=0) - world.min(axis=0)) >= min_size_bu:
                out[key + (k,)] = (m, local, mode, ob)
    return out


class Occluders:
    """Static occluders in one BVH, moving ones in a small BVH rebuilt per sample; answers which
    segments are blocked."""

    def __init__(self, scene, frames: list[float], min_size_m: float, scale: float, listener: str | None = None):
        snaps, cams, materials, parents = [], [], {}, []
        for f in frames:
            util.set_frame(scene, f)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            snaps.append(_snapshot(depsgraph, min_size_m / scale, materials))
            # instancers: also those of earlier snapshots' instances, which this one may lack (scaled to 0)
            parents.append(_instancers(set().union(*(_owners(sn) for sn in snaps)), depsgraph))
            cam = util.listener_object(scene, listener)
            cams.append(np.array(cam.evaluated_get(depsgraph).matrix_world) if cam else None)
        # instancers first seen at a later snapshot (their instance scaled to 0 at the start): their
        # matrices at the earlier ones, one more frame change each where there are any
        late = set().union(*(_owners(sn) for sn in snaps))
        for f, par in zip(frames, parents):
            need = {n for n in late if n not in par}
            if need:
                util.set_frame(scene, f)
                par.update(_instancers(need, bpy.context.evaluated_depsgraph_get()))
        # every snapshot's occluders, each with its entry from the first snapshot that has it
        first = {}
        for sn in snaps:
            for key, entry in sn.items():
                first.setdefault(key, entry)
        static, moving, carried = [], [], []
        for key, (m, local, _, _) in first.items():
            mats = [s[key][0] if key in s else None for s in snaps]
            if all(x is not None and np.allclose(x, m, atol=1e-4) for x in mats):
                static.append(key)
            elif _carried(mats, cams, local):
                carried.append(key)  # travels with the listener: its vehicle or cockpit, part of the listener
            else:
                moving.append(key)
        verts, tris, boxes = [], [], []
        for key in static:
            m, local, mode, ob = first[key]
            boxes.append((m, local))
            if mode == "mesh":
                me = ob.data
                me.calc_loop_triangles()
                co = np.array([tuple(v.co) for v in me.vertices]).reshape(-1, 3)
                verts.append(co @ m[:3, :3].T + m[:3, 3])
                tris.append(np.array([tuple(t.vertices) for t in me.loop_triangles], dtype=np.int64).reshape(-1, 3))
            else:
                verts.append(None)
                tris.append(None)
        self.static_keys = static  # occluder index -> (instancer, persistent id, object name, island)
        self.tree, self.static_owner = _tree(boxes, verts, tris)
        self.static_all = _box_arrays(boxes)  # every static occluder's box: containment and reflector tests
        self.static_solid = np.array([v is None for v in verts])  # occluders represented by their box
        self.moving_order = sorted(moving, key=lambda k: (k[0] or "", k[1], k[2], k[3]))  # plain objects: no instancer
        self.moving_local = [first[k][1] for k in self.moving_order]
        self.moving_mid = np.array([(c.min(axis=0) + c.max(axis=0)) / 2 for c in self.moving_local]).reshape(-1, 3)
        index = {k: i for i, k in enumerate(self.moving_order)}
        self.moving_objects = [(index[k], bpy.data.objects[k[2]]) for k in self.moving_order if k[0] is None]
        # instances rigid with their instancer: its matrix times a fixed relative matrix
        rows, owners, rel = [], [], []
        for k in self.moving_order:
            r = _relative(k, snaps, parents, min_size_m / scale) if k[0] is not None and BY_INSTANCER else None
            if r is not None:
                rows.append(index[k])
                owners.append(k[0])
                rel.append(r)
        self.rigid_parents = [bpy.data.objects[n] for n in dict.fromkeys(owners)]
        slot = {n: j for j, n in enumerate(dict.fromkeys(owners))}
        self.rigid_rows = np.array(rows, dtype=np.int64)
        self.rigid_owner = np.array([slot[n] for n in owners], dtype=np.int64)
        self.rigid_rel = np.array(rel).reshape(-1, 4, 4)
        rigid = set(rows)
        # the other instances by instancer and persistent id: reading inst.object in the per-sample walk
        # leaks memory in Blender 5.2 (see emitters.instance_key); one instance has one entry per island
        self.moving_instances: dict[tuple, list[int]] = {}
        for k in self.moving_order:
            if k[0] is not None and index[k] not in rigid:
                self.moving_instances.setdefault(k[:2], []).append(index[k])
        self.moving_parents = {k[0] for k in self.moving_instances}
        self.history_t: list[float] = []
        self.history_c: list[np.ndarray] = []
        self.moving_tree, self.moving_owner, self.moving_boxes, self.moving_keys = None, None, None, []
        self.counts = {"static": len(static), "moving": len(moving), "carried": len(carried)}
        self.walked = len(moving) - len(rows) - len(self.moving_objects)  # moving boxes found by the walk

    def update(self, depsgraph, time_s: float = 0.0, listener: np.ndarray | None = None,
               speed_bu: float | None = None) -> None:
        """Moving occluders at the current frame, each moved back to where it was when the sound now
        reaching the listener passed it (``time_s`` minus its distance to the listener over the
        speed of sound, from the centres of earlier samples). A source's own body is thus where it
        was at emission, around the emission point."""
        if not self.moving_order:
            return
        mats = np.full((len(self.moving_order), 4, 4), np.nan)  # NaN: not present at this frame
        evaluated: dict = {}
        for i, ob in self.moving_objects:
            if ob.hide_render:
                continue  # hidden at this frame, as in _snapshot (it may first appear later)
            if ob.name not in evaluated:
                evaluated[ob.name] = np.array(ob.evaluated_get(depsgraph).matrix_world)
            mats[i] = evaluated[ob.name]
        if len(self.rigid_rows):
            par = np.array([np.array(ob.evaluated_get(depsgraph).matrix_world) for ob in self.rigid_parents])
            mats[self.rigid_rows] = np.einsum("rij,rjk->rik", par[self.rigid_owner], self.rigid_rel)
        if self.moving_instances:
            for inst in depsgraph.object_instances:
                if inst.is_instance and inst.parent is not None and inst.parent.original.name in self.moving_parents:
                    rows = self.moving_instances.get((inst.parent.original.name, tuple(inst.persistent_id)))
                    if rows:
                        mats[rows] = inst.matrix_world
        present = ~np.isnan(mats[:, 0, 0])
        centres = np.einsum("mij,mj->mi", mats[:, :3, :3], self.moving_mid) + mats[:, :3, 3]
        self.history_t.append(time_s)
        self.history_c.append(centres)
        del self.history_t[:-HISTORY], self.history_c[:-HISTORY]
        if listener is not None and speed_bu and len(self.history_t) > 1:
            times, past = np.array(self.history_t), np.array(self.history_c)  # (K,), (K, M, 3)
            when = time_s - np.linalg.norm(centres - listener, axis=1) / speed_bu
            i = np.clip(np.searchsorted(times, when), 1, len(times) - 1)
            w = np.clip((when - times[i - 1]) / (times[i] - times[i - 1]), 0.0, 1.0)[:, None]
            cols = np.arange(len(centres))
            then = past[i - 1, cols] * (1 - w) + past[i, cols] * w
            mats[:, :3, 3] += np.where(np.isfinite(then), then - centres, 0.0)
        boxes = [(mats[i], self.moving_local[i]) for i in np.nonzero(present)[0]]
        self.moving_keys = [self.moving_order[i] for i in np.nonzero(present)[0]]
        self.moving_boxes = _box_arrays(boxes)
        self.moving_tree, self.moving_owner = _tree(boxes, [None] * len(boxes), [None] * len(boxes))

    def blocked(self, a: np.ndarray, b: np.ndarray, listener: np.ndarray | None = None,
                sources: np.ndarray | None = None, by: list | None = None) -> np.ndarray:
        """Segments a -> b (R, 3) that hit an occluder. With the path's ``listener`` and ``sources``
        (R, 3), an occluder does not block a path when its box contains the listener or the source
        (the emitter's own body, the camera's cockpit, a box too coarse to tell), or when it lies
        beyond both (a ground under both, a wall behind both: it reflects); the ray goes on past it.
        ``by`` (a list of R entries) receives the name of the object that blocks each segment."""
        hit = np.zeros(len(a), dtype=bool)
        for tree, owner, boxes, solid, keys in (
                (self.tree, self.static_owner, self.static_all, self.static_solid, self.static_keys),
                (self.moving_tree, self.moving_owner, self.moving_boxes, None, self.moving_keys)):
            if tree is None:
                continue
            passes: dict = {}
            for i in np.nonzero(~hit)[0]:
                d = Vector(b[i] - a[i])
                length = d.length * 0.999
                if length <= 1e-6:
                    continue
                direction, origin, gone = d.normalized(), Vector(a[i]), 0.0
                for _ in range(MAX_RECAST):
                    loc, _, face, dist = tree.ray_cast(origin, direction, length - gone)
                    if loc is None:
                        break
                    if listener is None:
                        hit[i] = True
                        break
                    j = int(owner[face])
                    key = (j, sources[i].tobytes())
                    if key not in passes:
                        boxed = solid is None or bool(solid[j])  # its box stands for it (not "mesh")
                        passes[key] = (boxed and (_inside(boxes, j, listener[i]) or _inside(boxes, j, sources[i]))
                                       or _reflector(boxes, j, listener[i], sources[i]))
                    if not passes[key]:
                        hit[i] = True
                        if by is not None:
                            by[i] = _label(keys[j])
                        break
                    step = dist + CLEARANCE_BU
                    origin, gone = origin + direction * step, gone + step
                    if gone >= length:
                        break
        return hit


def _owners(snap: dict) -> set:
    """Instancer names of a snapshot's instances."""
    return {k[0] for k in snap if k[0] is not None}


def _instancers(names: set, depsgraph) -> dict:
    """Evaluated world matrices of the instancer objects ``names``."""
    return {n: np.array(bpy.data.objects[n].evaluated_get(depsgraph).matrix_world) for n in names
            if n in bpy.data.objects}


def _relative(key: tuple, snaps: list[dict], parents: list[dict], min_size_bu: float) -> np.ndarray | None:
    """The instance's matrix relative to its instancer (from the first snapshot that has the key)
    when it is the same at every snapshot that has it, else None. A snapshot may lack the instance
    where its instancer makes it smaller than the minimum size: traffic scaled to zero while it jumps
    back, or before it first appears."""
    i0 = next(i for i, snap in enumerate(snaps) if key in snap)
    m, local, mode = snaps[i0][key][:3]
    p0 = parents[i0].get(key[0])
    if p0 is None or abs(np.linalg.det(p0[:3, :3])) < 1e-12:  # flattened: cannot tell
        return None
    rel = np.linalg.inv(p0) @ m
    for snap, par in zip(snaps, parents):
        p = par.get(key[0])
        if p is None:
            return None
        if key in snap:
            if not np.allclose(p @ rel, snap[key][0], rtol=1e-5, atol=1e-4):
                return None
        elif _counted(local, p @ rel, mode, min_size_bu):
            return None  # missing at its size: hidden or replaced, not scaled away
    return rel


def _counted(local: np.ndarray, m: np.ndarray, mode: str, min_size_bu: float) -> bool:
    """Whether ``_snapshot`` keeps a part with these local corners at matrix ``m``: its size times
    the largest column scale (the box parts' pre-test), then its world box."""
    if mode == "box" and (np.linalg.norm(local.max(axis=0) - local.min(axis=0))
                          < min_size_bu / max(np.linalg.norm(m[:3, :3], axis=0).max(), 1e-9)):
        return False
    world = local @ m[:3, :3].T
    return bool(np.linalg.norm(world.max(axis=0) - world.min(axis=0)) >= min_size_bu)


def _label(key: tuple) -> str:
    """Object name of an occluder key, with the instancer for instances."""
    return key[2] if key[0] is None else f"{key[0]}/{key[2]}"


def _carried(mats: list, cams: list, local: np.ndarray) -> bool:
    """Whether an object keeps its place relative to the listener (within its own size) at every
    snapshot while travelling further than that: the vehicle the camera rides on, a cockpit."""
    if any(m is None for m in mats) or any(c is None for c in cams):
        return False
    mid = (local.min(axis=0) + local.max(axis=0)) / 2
    world = np.array([m[:3, :3] @ mid + m[:3, 3] for m in mats])
    rel = np.array([np.linalg.solve(c, np.append(w, 1.0))[:3] for c, w in zip(cams, world)])
    size = max(float(np.linalg.norm(local.max(axis=0) - local.min(axis=0)) * np.linalg.norm(mats[0][:3, 0])), 2.0)
    return np.ptp(rel, axis=0).max() < size and np.ptp(world, axis=0).max() > size


def _reflector(boxes: dict, j: int, listener: np.ndarray, source: np.ndarray) -> bool:
    """Whether box j lies beyond both endpoints: both outside the same face, and no face plane
    between them (then it reflects, as the ground does; a wall or barrier between them has a face
    plane with the listener on one side and the source on the other)."""
    h = boxes["h"][j]
    lo = boxes["u"][j] @ (listener - boxes["c"][j])
    so = boxes["u"][j] @ (source - boxes["c"][j])
    same = np.any(((lo > h) & (so > h)) | ((lo < -h) & (so < -h)))
    between = np.any(((lo > h) & (so < -h)) | ((lo < -h) & (so > h)))
    return bool(same and not between)


def _tree(boxes: list, verts: list, tris: list) -> tuple[BVHTree | None, np.ndarray | None]:
    """One BVH over occluders, and the occluder index of each triangle. Each occluder is its
    oriented box (12 triangles) where ``verts[i]`` is None, else its triangles (world space)."""
    if not boxes:
        return None, None
    solid = np.array([i for i, v in enumerate(verts) if v is None], dtype=np.int64)
    all_verts, all_tris, owner = [], [], []
    if len(solid):
        m = np.array([boxes[i][0] for i in solid])
        local = np.array([boxes[i][1] for i in solid])
        corners = (np.einsum("mij,mkj->mki", m[:, :3, :3], local) + m[:, None, :3, 3])[:, BOX_ORDER]
        all_verts.append(corners.reshape(-1, 3))
        all_tris.append((BOX_FACES[None] + 8 * np.arange(len(solid))[:, None, None]).reshape(-1, 3))
        owner.append(np.repeat(solid, len(BOX_FACES)))
    offset = sum(len(v) for v in all_verts)
    for i, (v, tri) in enumerate(zip(verts, tris)):
        if v is not None:
            all_verts.append(v)
            all_tris.append(tri + offset)
            owner.append(np.full(len(tri), i))
            offset += len(v)
    tree = BVHTree.FromPolygons(np.concatenate(all_verts).tolist(), np.concatenate(all_tris).tolist(),
                                all_triangles=True)
    return tree, np.concatenate(owner)


def _box_arrays(boxes: list) -> dict | None:
    """Centres ``c`` (M, 3), unit axes ``u`` (M, 3, 3) as rows and half extents ``h`` (M, 3) of
    oriented boxes."""
    if not boxes:
        return None
    m = np.array([b[0] for b in boxes])  # (M, 4, 4)
    local = np.array([b[1] for b in boxes])  # (M, 8, 3) bounding-box corners
    lo, hi = local.min(axis=1), local.max(axis=1)
    r = m[:, :3, :3]
    size = np.linalg.norm(r, axis=1)  # scale per local axis (column norms)
    size = np.where(size > 1e-12, size, 1.0)
    c = np.einsum("mij,mj->mi", r, (lo + hi) / 2) + m[:, :3, 3]
    u = np.transpose(r / size[:, None, :], (0, 2, 1))
    h = np.maximum((hi - lo) / 2 * size, 1e-6)
    return {"c": c, "u": u, "h": h}


def _inside(boxes: dict, j: int, point: np.ndarray) -> bool:
    return bool(np.all(np.abs(boxes["u"][j] @ (point - boxes["c"][j])) <= boxes["h"][j]))


def fresnel_points(listener: np.ndarray, source: np.ndarray, scale: float, min_radius_m: float,
                   speed_of_sound: float = SPEED_OF_SOUND) -> np.ndarray:
    """Secondary-source points (1 + bands * points, 3) in Blender units: the direct-path midpoint,
    then per band the points on the median ring of the first Fresnel zone."""
    d_bu = source - listener
    dist_m = float(np.linalg.norm(d_bu)) * scale
    mid = (listener + source) / 2
    n = d_bu / max(np.linalg.norm(d_bu), 1e-9)
    helper = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(n, helper)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    pts = [mid]
    for b, f in enumerate(BANDS_HZ):
        radius_m = max(0.5 * math.sqrt(speed_of_sound / f * dist_m) / math.sqrt(2), min_radius_m)
        r = radius_m / scale
        for k in range(POINTS_PER_BAND):
            # rings turned 22.5, 37.5, 52.5 degrees: no two points of a band cross a horizontal or
            # vertical edge together, and no band's points sit on another band's
            phi = 2 * math.pi * k / POINTS_PER_BAND + math.radians(RING_OFFSET_DEG + RING_STEP_DEG * b)
            pts.append(mid + r * (math.cos(phi) * u + math.sin(phi) * v))
    return np.array(pts)


def retarded_positions(times: np.ndarray, positions: np.ndarray, listener: np.ndarray,
                       speed_of_sound: float) -> np.ndarray:
    """Where the sources were when they emitted the sound the listener hears at ``times[-1]``.

    Solves ``t_e = t - |x(t_e) - listener| / c`` by fixed-point iteration (converges for sources
    slower than sound), with positions linear between the samples so far: ``times`` (K,),
    ``positions`` (K, S, 3) and ``listener`` (3,) in metres. Before the first sample: the first.
    """
    x = positions[-1]
    if len(times) < 2:
        return x
    cols = np.arange(positions.shape[1])
    for _ in range(6):
        te = times[-1] - np.linalg.norm(x - listener, axis=1) / speed_of_sound
        i = np.clip(np.searchsorted(times, te), 1, len(times) - 1)
        w = np.clip((te - times[i - 1]) / (times[i] - times[i - 1]), 0.0, 1.0)[:, None]
        x = positions[i - 1, cols] * (1 - w) + positions[i, cols] * w
    return x


def direct_visibility(occluders: Occluders, listener: np.ndarray, sources: np.ndarray,
                      blockers: list | None = None) -> np.ndarray:
    """Visibility (S, bands) of sources (S, 3) from the direct path alone: 0 or 1, the same in every
    band (far-field sources, which use one broadband visibility). A blocked direct path counts as
    ``PATHS`` blocked paths in ``blockers``, so the shares stay comparable with ``visibility``."""
    lis = np.repeat(listener[None], len(sources), axis=0)
    by = [None] * len(sources) if blockers is not None else None
    open_ = ~occluders.blocked(lis, sources, lis, sources, by)
    if blockers is not None:
        for k, name in enumerate(by):
            if name is not None:
                blockers[k][name] += PATHS
    return np.repeat(open_.astype(np.float64)[:, None], len(BANDS_HZ), axis=1)


def visibility(occluders: Occluders, listener: np.ndarray, sources: np.ndarray, radii_m: list[float],
               scale: float, speed_of_sound: float = SPEED_OF_SOUND, blockers: list | None = None) -> np.ndarray:
    """Visibility (S, bands) of sources (S, 3) from the listener (3,), positions in Blender units.
    ``blockers`` (a list of S Counters) counts, per source, the blocked paths by object name."""
    n_pts = 1 + len(BANDS_HZ) * POINTS_PER_BAND
    pts = np.concatenate([fresnel_points(listener, s, scale, r, speed_of_sound)
                          for s, r in zip(sources, radii_m)])  # (S*n, 3)
    src = np.repeat(sources, n_pts, axis=0)
    lis = np.repeat(listener[None], len(pts), axis=0)
    # direct path: listener -> source; others: listener -> point -> source
    direct = (np.arange(len(pts)) % n_pts) == 0
    b1 = np.where(direct[:, None], src, pts)
    by1 = [None] * len(pts) if blockers is not None else None
    by2 = [None] * int((~direct).sum()) if blockers is not None else None
    open_ = ~occluders.blocked(lis, b1, lis, src, by1)
    open_[~direct] &= ~occluders.blocked(pts[~direct], src[~direct], lis[~direct], src[~direct], by2)
    if blockers is not None:
        names = np.array(by1, dtype=object)
        second = names[~direct]
        names[~direct] = np.where(second == None, np.array(by2, dtype=object), second)  # noqa: E711
        for k, name in enumerate(names):
            if name is not None:
                blockers[k // n_pts][name] += 1
    open_ = open_.reshape(len(sources), n_pts)
    out = np.empty((len(sources), len(BANDS_HZ)))
    for b in range(len(BANDS_HZ)):
        cols = [0] + list(range(1 + b * POINTS_PER_BAND, 1 + (b + 1) * POINTS_PER_BAND))
        out[:, b] = open_[:, cols].mean(axis=1)
    return out
