"""Tag and settings schema (Phase 1).

- Defaults in schema match the tables in docs/spec/tagging.md.
- Unknown key, wrong type, out-of-range value -> error naming the key.
- ``mode="once"`` without ``frame`` -> error; ``linear_clamped`` without ``max_distance`` -> error.
- ``resolve_source`` fills every key; resolved entry validates.
"""
