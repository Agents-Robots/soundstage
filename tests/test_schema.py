"""Tag and settings schema."""

import pytest

from soundstage.blender import schema


def test_minimal_entry_is_valid_and_resolves_every_key():
    entry = {"sample": "a.wav"}
    assert schema.validate_source(entry) == []
    r = schema.resolve_source(entry, default_id="Obj:0")
    assert set(r) == set(schema.SOURCE_KEYS)
    assert r["id"] == "Obj:0"
    assert r["mode"] == "loop" and r["distance_model"] == "inverse_clamped"
    assert schema.validate_source({k: v for k, v in r.items()}) == []


@pytest.mark.parametrize("entry, fragment", [
    ({}, "sample: required"),
    ({"sample": "a.wav", "gian_db": 3}, "unknown key 'gian_db'"),
    ({"sample": "a.wav", "gain_db": "loud"}, "gain_db: expected a number"),
    ({"sample": "a.wav", "spatial": 1}, "spatial: expected true/false"),
    ({"sample": "a.wav", "mode": "twice"}, "mode: 'twice' is not one of"),
    ({"sample": "a.wav", "ref_distance": 0}, "ref_distance: 0 is below the minimum"),
    ({"sample": "a.wav", "mode": "once"}, "frame: required for mode 'once'"),
    ({"sample": "a.wav", "distance_model": "linear_clamped"}, "max_distance: required"),
    ({"sample": "a.wav", "frame": [1, 2]}, "only allowed for mode 'once'"),
    ({"sample": "a.wav", "offset": [1, 2]}, "offset: expected three numbers"),
    ({"sample": "a.wav", "frame": 10, "end_frame": 5}, "end_frame: must not be before frame"),
])
def test_invalid_entries_name_the_problem(entry, fragment):
    errors = schema.validate_source(entry)
    assert any(fragment in e for e in errors), errors


def test_fade_in_default_depends_on_mode_and_frame():
    assert schema.resolve_source({"sample": "a", "mode": "once", "frame": 3})["fade_in"] == 0.0
    assert schema.resolve_source({"sample": "a"})["fade_in"] == 0.0
    assert schema.resolve_source({"sample": "a", "frame": 3})["fade_in"] == 0.05


def test_frame_list_is_sorted_floats():
    r = schema.resolve_source({"sample": "a", "mode": "once", "frame": [30, 10, 20]})
    assert r["frame"] == [10.0, 20.0, 30.0]


def test_settings_defaults_and_parse_value():
    s = schema.resolve_settings({})
    assert s["sample_rate"] == 48000 and s["speed_of_sound"] == 343.0
    assert schema.validate_settings({"sample_rate": 44100.5}) != []
    assert schema.parse_value("doppler_factor", "2") == 2.0
    assert schema.parse_value("listener", "none") is None
    with pytest.raises(ValueError):
        schema.parse_value("no_such_key", "1")


def test_unimplemented_reports_only_non_default_later_phase_keys():
    entry = schema.resolve_source({"sample": "a", "occlusion": False, "doppler": 2.0, "gain_db": -3})
    assert schema.unimplemented(entry, schema.SOURCE_KEYS) == ["occlusion"]
