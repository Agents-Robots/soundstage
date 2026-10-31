# Contributing

Bug reports, measurements and fixes are welcome. Work is tracked in this repository's
[GitHub issues](https://github.com/Agents-Robots/soundstage/issues).

## Reporting a problem

A render that sounds or measures wrong is easiest to fix from its scene file: attach (or describe
how to rebuild) `scene.json` and `scene.npz`, the command line, the `.report.json` and the version
(`git rev-parse HEAD`). A scene file can be built without Blender, see
[docs/spec/scene-format.md](docs/spec/scene-format.md#producing-scene-files-without-blender).

## Working on the code

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python tools/make_test_samples.py        # the samples the tests and examples use
.venv/bin/pytest -m "not blender"                  # unit tests, about a minute
.venv/bin/pytest                                   # plus the end-to-end tests (Blender 5.x on PATH)
.venv/bin/ruff check .                             # lint
```

The conventions, the layout of the documentation and the testing strategy are in
[AGENTS.md](AGENTS.md) (written for coding agents, binding for people too). In short:

- every behaviour is checked with numbers: known-answer tests with tolerances, no golden audio
  files; each numba kernel has a plain-numpy reference the tests compare against;
- a model change goes with its page in `research/models/`, the spec in `docs/spec/`, and an
  experiment in `research/experiments/` whose script reproduces every number quoted;
- defaults live in `soundstage/blender/schema.py` and are documented in the specs;
- `soundstage/blender/` imports only `bpy` and the standard library (plus Blender's numpy);
  `soundstage/engine/` never imports `bpy`.

Commit messages say what changed and why, in plain technical language.
