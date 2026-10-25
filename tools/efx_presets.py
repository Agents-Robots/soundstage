"""Convert the EFX reverb presets (OpenAL Soft's include/AL/efx-presets.h) into the engine's JSON table.

    python3 tools/efx_presets.py efx-presets.h > soundstage/engine/data/efx_presets.json

The presets are the I3DL2/EAX reverb parameter sets known from OpenAL, DirectSound, FMOD and game
engines (Creative's EAX environment presets as published with OpenAL Soft). The engine synthesizes
an impulse response from them (engine/reverb.py). Field order follows EFXEAXREVERBPROPERTIES.
"""

from __future__ import annotations

import json
import re
import sys

FIELDS = ["density", "diffusion", "gain", "gain_hf", "gain_lf", "decay_time", "decay_hf_ratio", "decay_lf_ratio",
          "reflections_gain", "reflections_delay", "reflections_pan", "late_reverb_gain", "late_reverb_delay",
          "late_reverb_pan", "echo_time", "echo_depth", "modulation_time", "modulation_depth",
          "air_absorption_gain_hf", "hf_reference", "lf_reference", "room_rolloff_factor", "decay_hf_limit"]


def parse(text: str) -> dict:
    presets = {}
    for m in re.finditer(r"#define\s+EFX_REVERB_PRESET_(\w+)\s*\\?\s*\{(.*?)\}\s*\n", text, re.S):
        body = m.group(2) + "}"
        numbers = [float(x) if not x.startswith("0x") else int(x, 16)
                   for x in re.findall(r"0x[0-9a-fA-F]+|-?\d+\.?\d*(?:[eE]-?\d+)?", body)]
        if len(numbers) != len(FIELDS) + 4:  # two 3-vectors count as one field each
            continue
        values, i = {}, 0
        for f in FIELDS:
            if f.endswith("_pan"):
                values[f], i = numbers[i:i + 3], i + 3
            else:
                values[f], i = numbers[i], i + 1
        values["decay_hf_limit"] = bool(values["decay_hf_limit"])
        presets[m.group(1).lower()] = values
    return presets


def main() -> None:
    presets = parse(open(sys.argv[1]).read())
    json.dump({"source": "EFX reverb presets as published in OpenAL Soft include/AL/efx-presets.h "
                         "(I3DL2/EAX environment presets); converted by tools/efx_presets.py",
               "fields": FIELDS, "presets": presets}, sys.stdout, indent=1)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
