"""Scene file loading and time base."""

import json

import numpy as np
import pytest

from soundstage.engine import render
from soundstage.engine.scene import SceneError, load_scene, parse_overrides


def test_round_trip(make_scene, sine):
    scene = make_scene([{"sample": sine}], [[0, 10, 0]])
    assert scene.sources[0].id == "source:0" and scene.sources[0].track == 0
    assert scene.src_pos.shape == (61, 1, 3)
    assert np.allclose(scene.src_pos[:, 0], [0, 10, 0])


def test_unknown_version_is_rejected(make_scene, sine):
    scene = make_scene([{"sample": sine}])
    manifest = json.loads(scene.path.read_text())
    manifest["version"] = 99
    scene.path.write_text(json.dumps(manifest))
    with pytest.raises(SceneError, match="unsupported version"):
        load_scene(scene.path)


def test_version_1_files_still_load_and_screen_panning_warns(make_scene, sine):
    scene = make_scene([{"sample": sine}], [[0, 10, 0]], settings={"pan_reference": "screen"})
    manifest = json.loads(scene.path.read_text())
    manifest["version"] = 1
    scene.path.write_text(json.dumps(manifest))
    old = load_scene(scene.path)
    assert old.listener_frame is None
    out = render.render(old, frames=(1, 5))
    assert any("no frame edges" in w for w in out.warnings)


def test_listener_frame_shape_is_checked(make_scene, sine):
    with pytest.raises(SceneError, match="listener_frame"):
        make_scene([{"sample": sine}], frame=np.zeros((3, 2)))


def test_overrides_are_typed_and_validated(make_scene, sine):
    scene = make_scene([{"sample": sine}])
    assert load_scene(scene.path, parse_overrides(["master_gain_db=-6"])).settings["master_gain_db"] == -6.0
    with pytest.raises(SceneError):
        parse_overrides(["nonsense=1"])
    with pytest.raises(SceneError):
        load_scene(scene.path, parse_overrides(["panner=surround"]))


def test_frame_120_at_30fps_is_sample_190400(make_scene, sine):
    scene = make_scene([{"sample": sine}], frame_end=240)
    assert scene.sample_of(120) == 190400


@pytest.mark.parametrize("fps, fps_base, frames, seconds", [
    (24, 1.0, 240, 10.0),
    (25, 1.0, 250, 10.0),
    (30, 1.0, 300, 10.0),
    (30, 1.001, 300, 10.01),
    (24, 1.001, 24000, 1001.0),
])
def test_output_length(make_scene, sine, fps, fps_base, frames, seconds):
    scene = make_scene([{"sample": sine}], frame_end=frames, fps=fps, fps_base=fps_base)
    assert scene.length_samples() == round(seconds * 48000)


@pytest.mark.parametrize("change, fragment", [
    (lambda a: a.pop("listener_matrix"), "'listener_matrix' missing"),
    (lambda a: a.update(listener_matrix=a["listener_matrix"][:-1]), "'listener_matrix' has shape"),
    (lambda a: a.update(src_pos=a["src_pos"][:, :, :2]), "'src_pos' has shape"),
    (lambda a: a.update(frames=a["frames"][::-1].copy()), "strictly increasing"),
    (lambda a: a.update(vis_frames=np.arange(3.0)), "go together"),
])
def test_malformed_arrays_are_refused(make_scene, sine, change, fragment):
    scene = make_scene([{"sample": sine}], [[0, 10, 0]])
    npz = scene.path.parent / "scene.npz"
    with np.load(npz) as a:
        arrays = {k: a[k] for k in a.files}
    change(arrays)
    np.savez(npz, **arrays)
    with pytest.raises(SceneError, match=fragment):
        load_scene(scene.path)
