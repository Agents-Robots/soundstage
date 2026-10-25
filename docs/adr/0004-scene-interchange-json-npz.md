# 0004. Scene interchange as versioned JSON manifest plus NPZ arrays

- Status: Accepted
- Date: 2026-10-25
- Ticket: —

## Context

The bake (in Blender's Python) and the engine (in the venv) exchange settings, resolved tags and
trajectories. Trajectories are large: a 5-minute shot at 30 fps with 4 sub-frames, 3 s padding
and 50 sources is ~37 000 time samples × 50 × 3 coordinates, plus listener matrices. The exchange
must be writable from Blender with what it ships (numpy, stdlib), readable by people and agents
for debugging, and writable by tests without Blender.

## Decision

A shot directory with two files ([spec/scene-format.md](../spec/scene-format.md)):

- `scene.json`: format name and integer version, time base, unit scale, resolved settings, the
  source list with every parameter resolved (defaults filled, sample paths absolute), warnings.
- `scene.npz`: numpy arrays for frames, listener matrices, cuts, source positions, forward
  vectors, visibility; float64 for positions.

## Alternatives considered

- **One JSON file with arrays inline**: simple, but tens of MB of text, slow to parse, float
  round-trip concerns.
- **HDF5**: good for arrays and metadata in one file, but h5py is not in Blender's Python.
- **USD**: Blender exports it, but audio and per-sub-frame custom data are not established there,
  and it would bring a heavy dependency to the engine.
- **The engine reading the .blend directly**: impossible without Blender evaluating the depsgraph.

## Consequences

- The manifest is diffable and readable (`soundstage inspect` adds a summary on top).
- Resolving defaults in the bake means the engine never needs to know Blender's or the tag
  helper's defaults, but both read them from the same schema module.
- Any change of meaning bumps `version`; the engine rejects unknown versions instead of guessing.
- Two files must be kept together; the manifest names its NPZ file.
