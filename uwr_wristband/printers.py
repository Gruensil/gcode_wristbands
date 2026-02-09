from __future__ import annotations

import json
from functools import lru_cache
from importlib import import_module, resources
from typing import Dict, List, Tuple


# Community singletool printers (bare module names, no prefix).
# These are the printers in fullcontrol/devices/community/singletool/ that have
# a set_up() function.  Excludes base_settings, custom, generic, __init__,
# toolchanger_*, and wasp2040clay (niche).
COMMUNITY_PRINTERS: Dict[str, str] = {
    "Anycubic Kobra 3": "anycubic_kobra3",
    "Bambu Lab X1": "bambulab_x1",
    "Creality CR-10": "cr_10",
    "Creality Ender 3": "ender_3",
    "Creality Ender 5 Plus": "ender_5_plus",
    "Prusa i3": "prusa_i3",
    "Prusa Mini": "prusa_mini",
    "Prusa MK4": "prusa_mk4",
    "Raise3D Pro2 (Nozzle 1)": "raise3d_pro2_nozzle1",
    "Ultimaker 2+": "ultimaker2plus",
    "Voron Zero": "voron_zero",
    "Generic": "generic",
}


@lru_cache(maxsize=1)
def _load_cura_library() -> Dict[str, str]:
    """Load the Cura library.json: {display_name: printer_id}."""
    resource = resources.files("fullcontrol") / "devices" / "cura" / "library.json"
    with resource.open("r") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def get_all_printer_options() -> Tuple[Tuple[str, str], ...]:
    """Return a tuple of (display_label, fc_printer_name) for all printers.

    ``fc_printer_name`` is the value to pass to
    ``fc.GcodeControls(printer_name=...)``.

    - Community printers: bare module name (e.g. ``"anycubic_kobra3"``)
    - Cura printers: ``"Cura/{display_name}"``

    Community printers are listed first (recommended / tested), then Cura
    printers sorted alphabetically.
    """
    options: List[Tuple[str, str]] = []

    for display, module_name in COMMUNITY_PRINTERS.items():
        options.append((display, module_name))

    try:
        cura = _load_cura_library()
        for display_name in sorted(cura.keys()):
            options.append((f"{display_name} (Cura)", f"Cura/{display_name}"))
    except Exception:
        pass  # Cura library not available — community printers only

    return tuple(options)


def default_printer_index() -> int:
    """Return the index of the default printer (Anycubic Kobra 3) in the
    options list."""
    options = get_all_printer_options()
    for i, (_, fc_name) in enumerate(options):
        if fc_name == "anycubic_kobra3":
            return i
    return 0


@lru_cache(maxsize=64)
def get_build_volume(fc_printer_name: str) -> Tuple[float, float, float]:
    """Return ``(build_volume_x, build_volume_y, build_volume_z)`` in mm.

    Works for both community printers (bare module name) and Cura printers
    (``"Cura/{display_name}"`` format).  Falls back to ``(250, 250, 250)``
    if the data cannot be loaded.
    """
    try:
        if fc_printer_name.startswith("Cura/"):
            display_name = fc_printer_name[5:]
            cura_lib = _load_cura_library()
            printer_id = cura_lib[display_name]
            mod = import_module(
                f"fullcontrol.devices.cura.settings.{printer_id}"
            )
            s = mod.default_initial_settings
        else:
            mod = import_module(
                f"fullcontrol.devices.community.singletool.{fc_printer_name}"
            )
            s = mod.printer_overrides
        return (
            float(s.get("build_volume_x", 250)),
            float(s.get("build_volume_y", 250)),
            float(s.get("build_volume_z", 250)),
        )
    except Exception:
        return (250.0, 250.0, 250.0)
