# Tests

- Unit tests run without Blender: `.venv/bin/pytest`.
- End-to-end tests call `blender -b`: `.venv/bin/pytest -m blender`.
- Synthetic scenes are written with `soundstage.engine.scene.write_scene` (fixture `make_scene` in
  `conftest.py`); Blender scenes are built by scripts inside the test modules, never stored .blend
  files.
- Tests assert measured quantities with tolerances (level, balance, onset sample, frequency),
  not golden audio files. Each numba kernel is checked against its numpy reference.

Each `test_*.py` says in its module docstring what it covers. Tolerances come from [docs/roadmap.md](../docs/roadmap.md) acceptance criteria and
[docs/requirements.md](../docs/requirements.md) NFR-9.
