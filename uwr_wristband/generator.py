"""Core wristband generation logic.

Extracted and optimised from ``fullcontrol/models/armband_v4.py``.  The main
change is replacing the per-point Python loop in
``generate_spiral_meander_with_side_emboss`` with vectorised shapely 2.0
``contains_xy`` calls for a ~10x speed-up.
"""

from __future__ import annotations

import logging
import math
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from uwr_wristband import BAND_VERSION
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from matplotlib.transforms import Affine2D
from shapely import contains_xy
from shapely.affinity import scale
from shapely.geometry import MultiPolygon, Polygon

import fullcontrol as fc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text polygons (Y, Z space)
# ---------------------------------------------------------------------------

def build_text_multipolygon(
    text: str,
    font: str,
    size: float,
    position: Tuple[float, float],
    mirror: bool = False,
) -> MultiPolygon:
    """Build a shapely MultiPolygon for *text* in (Y, Z) coordinates."""
    fp = FontProperties(family=font, size=size, weight="bold")
    tp = TextPath((0, 0), text, prop=fp)

    bbox = tp.get_extents()
    width = bbox.width
    height = bbox.height

    transform = Affine2D().translate(
        position[0] - width / 2.0, position[1] - height / 2.0
    )
    raw_polys = tp.to_polygons()

    transformed = [transform.transform(p) for p in raw_polys if len(p) >= 3]
    shapely_polys = [Polygon(p) for p in transformed]

    # Group holes robustly by sorting by area (largest first) and nesting
    outers: List[Polygon] = []
    used: set[int] = set()

    valid_polys = [
        (i, poly)
        for i, poly in enumerate(shapely_polys)
        if poly.is_valid and poly.area > 0
    ]
    valid_polys.sort(key=lambda x: x[1].area, reverse=True)

    for i, outer in valid_polys:
        if i in used:
            continue
        holes = []
        for j, inner in valid_polys:
            if j == i or j in used:
                continue
            buffered_outer = outer.buffer(0.0001)
            if buffered_outer.contains(inner):
                coords = list(inner.exterior.coords)
                if inner.exterior.is_ccw:
                    coords.reverse()
                holes.append(coords)
                used.add(j)

        used.add(i)
        try:
            cleaned = Polygon(outer.exterior.coords, holes).buffer(0)
            if cleaned.is_valid and cleaned.area > 0:
                if isinstance(cleaned, MultiPolygon):
                    outers.extend(list(cleaned.geoms))
                else:
                    outers.append(cleaned)
        except Exception:
            cleaned = outer.buffer(0)
            if cleaned.is_valid and cleaned.area > 0:
                outers.append(cleaned)

    polygon = MultiPolygon(outers)
    if mirror:
        polygon = scale(polygon, xfact=-1, yfact=1, origin="center")
    return polygon


# ---------------------------------------------------------------------------
# Spiral generation (vectorised)
# ---------------------------------------------------------------------------

def calculate_scale_factor(
    phi_max: float, wiggle_frequency: float, num_points: int = 10_000
) -> float:
    """Estimate a scale factor so the theta integral covers 2*pi per turn."""
    t = np.linspace(0.0, 2.0 * np.pi, num_points)
    dt = t[1] - t[0]
    cos_vals = np.cos(phi_max * np.sin(wiggle_frequency * t))
    integral = np.sum(cos_vals) * dt
    if abs(integral) < 1e-12:
        return 1.0
    return 2.0 * np.pi / integral


def generate_spiral_meander_with_side_emboss(
    total_height: float,
    base_radius: float,
    wiggle_amplitude: float,
    wiggle_frequency: float,
    spiral_layer_thickness: float,
    center_point: Tuple[float, float],
    text_front: Optional[str],
    text_back: Optional[str],
    text_font: str = "DejaVu Sans",
    text_size: float = 1.0,
    text_position_yz: Tuple[float, float] = (0.0, 0.0),
    num_points: int = 200_000,
    phi_max: float = math.pi * 0.59,
    start_shift_turns: float = 1.0,
    initial_z: float = 0.14,
) -> List[Tuple[float, float, float]]:
    """Generate a spiral (x, y, z) point list with sinusoidal radial wiggle.

    Text regions are detected using vectorised ``shapely.contains_xy`` (shapely
    >= 2.0) instead of per-point ``Polygon.contains(Point(...))``, giving
    roughly a 10x speed-up for 100k+ points.
    """
    # Build text polygons in (Y, Z) space
    text_front_poly = None
    text_back_poly = None
    if text_front:
        text_front_poly = build_text_multipolygon(
            text_front, text_font, text_size, text_position_yz, mirror=False
        )
    if text_back:
        text_back_poly = build_text_multipolygon(
            text_back, text_font, text_size, text_position_yz, mirror=True
        )

    turns = float(total_height) / float(spiral_layer_thickness)
    t = np.linspace(0.0, turns * 2.0 * np.pi, int(num_points))

    cos_vals = np.cos(phi_max * np.sin(wiggle_frequency * t))
    sin_vals = np.sin(phi_max * np.sin(wiggle_frequency * t))
    dt = np.gradient(t)

    factor = calculate_scale_factor(phi_max, wiggle_frequency)
    theta = factor * np.cumsum(cos_vals * dt)
    d_r = wiggle_amplitude * np.cumsum(sin_vals * dt)

    cx, cy = center_point

    z_shift = start_shift_turns * spiral_layer_thickness
    z_vals = (t / (2.0 * math.pi)) * spiral_layer_thickness + initial_z - z_shift
    z_vals = np.maximum(z_vals, initial_z)

    # Test positions (before text emboss scaling)
    r_test = base_radius + d_r
    x_test = r_test * np.cos(theta)
    y_test = r_test * np.sin(theta)

    # --- Vectorised text containment via shapely 2.0 ---
    in_text = np.zeros(len(t), dtype=bool)

    if text_front_poly is not None:
        front_mask = x_test >= 0
        if np.any(front_mask):
            in_text[front_mask] |= contains_xy(
                text_front_poly, y_test[front_mask], z_vals[front_mask]
            )

    if text_back_poly is not None:
        back_mask = x_test <= 0
        if np.any(back_mask):
            in_text[back_mask] |= contains_xy(
                text_back_poly, y_test[back_mask], z_vals[back_mask]
            )

    # Apply text emboss scaling
    d_r_final = d_r.copy()
    d_r_final[in_text] *= 1.6

    r = base_radius + d_r_final
    x = cx + r * np.cos(theta)
    y = cy + r * np.sin(theta)
    z_out = np.maximum(z_vals, initial_z)

    return list(zip(x.tolist(), y.tolist(), z_out.tolist()))


# ---------------------------------------------------------------------------
# Convert points into fullcontrol steps
# ---------------------------------------------------------------------------

def build_steps_from_points(
    spiral_points: Sequence[Tuple[float, float, float]],
    EW: float,
    EH: float,
    initial_z: float,
    reduced_fan_percent: int,
    reduced_print_speed_factor: float,
    print_speed: float,
    fan_percent: int,
    ease_in_height: float,
    ease_out_height: float,
    ease_strength: float,
    startup_height: float,
) -> List:
    """Build a list of FullControl step objects from (x, y, z) points."""
    local_steps: list = []
    local_steps.append(fc.StationaryExtrusion(volume=-1.5, speed=250))
    local_steps.append(fc.Extruder(on=False))
    local_steps.append(
        fc.Point(x=spiral_points[0][0], y=spiral_points[0][1], z=initial_z)
    )
    local_steps.append(fc.Extruder(on=True))
    local_steps.append(fc.Fan(speed_percent=reduced_fan_percent))
    local_steps.append(
        fc.Printer(print_speed=print_speed * reduced_print_speed_factor)
    )

    usable_height = max(0.0, float(max(p[2] for p in spiral_points)))
    current_width = None
    current_fan = reduced_fan_percent
    current_speed = print_speed * reduced_print_speed_factor

    for pt in spiral_points:
        z = pt[2]
        if z <= initial_z:
            z = initial_z
        rel_z = min(max(z - initial_z, 0.0), usable_height)

        if rel_z >= startup_height:
            if current_fan != fan_percent:
                local_steps.append(fc.Fan(speed_percent=fan_percent))
                current_fan = fan_percent
            if current_speed != print_speed:
                local_steps.append(fc.Printer(print_speed=print_speed))
                current_speed = print_speed

        width = EW
        if ease_in_height > 0 and rel_z < ease_in_height:
            t = rel_z / float(ease_in_height)
            ease_val = 0.5 * (1 - math.cos(math.pi * t))
            width = EW * (1 - ease_strength + ease_strength * ease_val)
        elif ease_out_height > 0 and rel_z > (usable_height - ease_out_height):
            dist_from_end = usable_height - rel_z
            t = dist_from_end / float(ease_out_height)
            ease_val = 0.5 * (1 - math.cos(math.pi * t))
            width = EW * (1 - ease_strength + ease_strength * ease_val)

        w_rounded = round(width, 4)
        if w_rounded != current_width:
            local_steps.append(fc.ExtrusionGeometry(width=w_rounded, height=EH))
            current_width = w_rounded

        local_steps.append(fc.Point(x=pt[0], y=pt[1], z=z))

    local_steps.append(fc.Extruder(on=False))
    local_steps.append(fc.StationaryExtrusion(volume=-1.5, speed=250))
    return local_steps


# ---------------------------------------------------------------------------
# Grid assembly
# ---------------------------------------------------------------------------

def assemble_grid_steps(
    params: dict,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> List:
    """Assemble a grid of spirals into a single fullcontrol steps list.

    ``progress_callback(current, total)`` is called after each spiral so the
    caller can update a progress bar.
    """
    grid_first_center = params["grid_first_center"]
    grid_nx = params["grid_nx"]
    grid_ny = params["grid_ny"]
    grid_spacing = params["grid_spacing"]
    spiral_configs = params.get("spiral_configs", [])

    total_spirals = sum(
        1
        for idx in range(grid_nx * grid_ny)
        if idx < len(spiral_configs) and spiral_configs[idx] is not None
    )

    steps: List = []
    spiral_index = 0
    completed = 0
    for iy in range(grid_ny):
        for ix in range(grid_nx):
            idx = spiral_index
            spiral_index += 1

            if idx >= len(spiral_configs) or spiral_configs[idx] is None:
                continue

            config = spiral_configs[idx]
            cx = grid_first_center[0] + ix * grid_spacing[0]
            cy = grid_first_center[1] + iy * grid_spacing[1]

            circ = config.get("circumference", params["circumference"])
            front_text = config.get("text_front", params["text_front"])
            back_text = config.get("text_back", params["text_back"])

            if back_text is not None:
                back_text = str(back_text)

            base_r = circ / (2.0 * math.pi)

            pts = generate_spiral_meander_with_side_emboss(
                total_height=params["total_height"],
                base_radius=base_r,
                wiggle_amplitude=params["wiggle_amplitude"],
                wiggle_frequency=params["wiggle_frequency"],
                spiral_layer_thickness=params["spiral_layer_thickness"],
                center_point=(cx, cy),
                text_front=front_text,
                text_back=back_text,
                text_font=params.get("text_font", "DejaVu Sans"),
                text_size=params.get("text_size", 1.0),
                text_position_yz=params.get("text_position_yz", (0.0, 0.0)),
                num_points=params.get("num_points_per_spiral", 100_000),
                phi_max=params.get("phi_max", math.pi * 0.59),
                start_shift_turns=params.get("start_shift_turns", 1.0),
                initial_z=params.get("initial_z", 0.14),
            )

            local = build_steps_from_points(
                spiral_points=pts,
                EW=params["EW"],
                EH=params["EH"],
                initial_z=params["initial_z"],
                reduced_fan_percent=params["reduced_fan_percent"],
                reduced_print_speed_factor=params["reduced_print_speed_factor"],
                print_speed=params["print_speed"],
                fan_percent=params["fan_percent"],
                ease_in_height=params["ease_in_height"],
                ease_out_height=params["ease_out_height"],
                ease_strength=params["ease_strength"],
                startup_height=params["startup_height"],
            )

            local.append(fc.Printer(print_speed=params["print_speed"]))
            local.append(fc.Fan(speed_percent=params["fan_percent"]))
            steps.extend(local)

            steps.append(fc.Extruder(on=False))
            steps.append(fc.Point(x=cx, y=cy, z=params["safe_z"]))

            is_last = (
                iy == params["grid_ny"] - 1 and ix == params["grid_nx"] - 1
            )
            if not is_last:
                if ix < (params["grid_nx"] - 1):
                    next_ix, next_iy = ix + 1, iy
                else:
                    next_ix, next_iy = 0, iy + 1

                next_idx = idx + 1
                next_cx = (
                    params["grid_first_center"][0]
                    + next_ix * params["grid_spacing"][0]
                )
                next_cy = (
                    params["grid_first_center"][1]
                    + next_iy * params["grid_spacing"][1]
                )

                next_circ = params["circumference"]
                for check_idx in range(next_idx, len(spiral_configs)):
                    if spiral_configs[check_idx] is not None:
                        next_circ = spiral_configs[check_idx].get(
                            "circumference", next_circ
                        )
                        break

                next_base_r = next_circ / (2.0 * math.pi)
                next_start_x = next_cx + next_base_r
                next_start_y = next_cy
                steps.append(
                    fc.Point(
                        x=next_start_x,
                        y=next_start_y,
                        z=params["safe_z"],
                    )
                )

            completed += 1
            if progress_callback is not None:
                progress_callback(completed, total_spirals)

    return steps


# ---------------------------------------------------------------------------
# High-level convenience functions
# ---------------------------------------------------------------------------

def build_params(
    *,
    text_front: str = "SILERS",
    text_back: str = "19",
    circumference: float = 165.0,
    printer_name: str = "anycubic_kobra3",
    nozzle_temp: int = 220,
    bed_temp: int = 60,
    print_speed: int = 1100,
    fan_percent: int = 30,
    EW: float = 0.5,
    EH: float = 0.2,
    total_height: float = 18.0,
    wiggle_amplitude: float = 50.0,
    wiggle_frequency: float = 80.0,
    text_size: float = 10.0,
    ease_in_height: float = 0.8,
    ease_out_height: float = 0.8,
    ease_strength: float = 0.95,
    num_points_per_spiral: int = 100_000,
    grid_nx: int = 1,
    grid_ny: int = 1,
    grid_spacing_x: float = 90.0,
    grid_spacing_y: float = 86.0,
    spiral_configs: Optional[list] = None,
) -> dict:
    """Build a complete params dict from user-facing values.

    ``spiral_configs`` is a list of length ``grid_nx * grid_ny``.  Each entry
    is either a dict ``{"text_front": ..., "text_back": ..., "circumference": ...}``
    or ``None`` for empty grid slots that should be skipped.
    """
    from .defaults import DEFAULTS

    params = DEFAULTS.copy()
    params.update(
        {
            "text_front": text_front,
            "text_back": text_back,
            "circumference": circumference,
            "printer_name": printer_name,
            "nozzle_temp": nozzle_temp,
            "bed_temp": bed_temp,
            "print_speed": print_speed,
            "fan_percent": fan_percent,
            "EW": EW,
            "EH": EH,
            "total_height": total_height,
            "wiggle_amplitude": wiggle_amplitude,
            "wiggle_frequency": wiggle_frequency,
            "text_size": text_size,
            "text_position_yz": (0.0, 0.5 * total_height),
            "ease_in_height": ease_in_height,
            "ease_out_height": ease_out_height,
            "ease_strength": ease_strength,
            "num_points_per_spiral": num_points_per_spiral,
            "grid_nx": grid_nx,
            "grid_ny": grid_ny,
            "grid_spacing": (grid_spacing_x, grid_spacing_y),
        }
    )

    # Derived values
    params["initial_z"] = params["EH"] * params.get("initial_z_factor", 0.7)
    params["safe_z"] = params["total_height"] + 10.0
    params["spiral_layer_thickness"] = params["EH"]

    # Build spiral_configs — default to a single band if not provided
    if spiral_configs is not None:
        params["spiral_configs"] = spiral_configs
    else:
        params["spiral_configs"] = [
            {
                "circumference": circumference,
                "text_front": text_front,
                "text_back": text_back,
            }
        ]

    is_single = grid_nx == 1 and grid_ny == 1
    if is_single:
        # Center single band on a typical 255x255 bed
        params["center_point"] = (127.5, 127.5)
        params["grid_first_center"] = (127.5, 127.5)
    else:
        params["grid_first_center"] = (40.0, 48.0)

    return params


def generate_gcode_string(
    params: dict,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Generate G-code as a string (no file written to disk)."""
    steps = assemble_grid_steps(params, progress_callback=progress_callback)

    gcode_controls = fc.GcodeControls(
        printer_name=params["printer_name"],
        save_as=None,
        initialization_data={
            "primer": "front_lines_then_y",
            "print_speed": params["print_speed"],
            "nozzle_temp": params["nozzle_temp"],
            "bed_temp": params["bed_temp"],
            "fan_percent": params["fan_percent"],
            "extrusion_width": params["EW"],
            "extrusion_height": params["EH"],
        },
    )

    gcode = fc.transform(steps, "gcode", gcode_controls, show_tips=False)

    # Prepend a version header so prints can be traced to the generator revision.
    header = (
        f"; UWR Wristband Generator — band version {BAND_VERSION}\n"
        f"; https://github.com/gruensil/gcode_wristbands\n"
    )
    return header + gcode
