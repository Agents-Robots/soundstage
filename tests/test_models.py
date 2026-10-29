"""Model registries match the schema's choices (ADR 0009)."""

from soundstage.blender import schema
from soundstage.engine import filters, panning, propagation


def test_schema_choices_match_registries():
    assert set(schema.PANNERS) == set(panning.PANNERS)
    assert set(schema.PAN_LAWS) == set(panning.PAN_LAWS)
    assert set(schema.QUALITIES) == set(propagation.QUALITY)
    assert set(schema.DISTANCE_MODELS) == set(filters.DISTANCE_MODELS)
    assert set(propagation.QUALITY.values()) <= set(propagation.INTERPOLATORS)


def test_only_phase4_keys_are_unimplemented():
    later = {k for k, f in {**schema.SOURCE_KEYS, **schema.SCENE_SETTINGS}.items() if f.phase > schema.IMPLEMENTED_PHASE and k not in schema.IMPLEMENTED_LATER}
    assert later == {"variants", "gain_jitter_db", "pitch_jitter", "gain_prop", "pitch_prop"}
