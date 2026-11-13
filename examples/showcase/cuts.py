"""The cuts of the showcase (sections/README.md, "Cuts"): section keys in order. ``key:body`` takes the
section without its title page. Nothing else depends on the order."""

FULL = ("intro", "sources", "distance", "delay", "doppler", "around", "screen", "directivity", "occlusion", "reverb",
        "cuts", "scale", "finale", "outro")
CUTS = {
    "full": FULL,
    "trailer": ("finale:body", "outro"),
}
