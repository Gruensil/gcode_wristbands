from __future__ import annotations

import math

DEFAULTS = {
    # printer / gcode
    "design_name": "uwr_wristband",
    "nozzle_temp": 220,
    "bed_temp": 60,
    "print_speed": 1100,  # mm/min
    "fan_percent": 30,
    "printer_name": "prusa_mk4",

    # geometry
    "EW": 0.5,  # extrusion width [mm]
    "EH": 0.2,  # extrusion height / layer height [mm]
    "initial_z_factor": 0.7,  # initial_z = EH * initial_z_factor
    "total_height": 18.0,  # mm
    "circumference": 165.0,  # mm
    "wiggle_amplitude": 50.0,  # mm
    "wiggle_frequency": 80.0,  # cycles around spiral
    "spiral_layer_thickness": 0.2,  # mm
    "center_point": (150.0, 150.0),  # mm

    # text
    "text_size": 10.0,
    "text_position_yz": (0.0, 0.5 * 18.0),
    "text_front": "TEST",
    "text_back": "123",
    "text_font": "DejaVu Sans",

    # ease-in/out and startup
    "ease_in_height": 4 * 0.2,
    "ease_out_height": 4 * 0.2,
    "ease_strength": 0.95,
    "startup_height": 1.0,
    "reduced_print_speed_factor": 0.5,
    "reduced_fan_percent": 10,

    # sampling
    "num_points_per_spiral": 100_000,
    "phi_max": math.pi * 0.59,
    "start_shift_turns": 1.0,

    # grid for multiple bands
    "grid_first_center": (40.0, 48.0),
    "grid_nx": 3,
    "grid_ny": 3,
    "grid_spacing": (90.0, 86.0),
}

SIZE_PRESETS = {
    "XS (140mm)": 140.0,
    "S (150mm)": 150.0,
    "M (160mm)": 160.0,
    "L (170mm)": 170.0,
    "XL (180mm)": 180.0,
    "Custom": None,
}

QUALITY_PRESETS = {
    "Fast (50k points)": 50_000,
    "Standard (100k points)": 100_000,
    "High (150k points)": 150_000,
}

MIN_CIRCUMFERENCE = 120.0
MAX_CIRCUMFERENCE = 250.0
MAX_TEXT_LENGTH = 20
MAX_BANDS = 9
