"""UWR-wristband logo — a meander band with googly eyes peeking out."""

from __future__ import annotations

import math


def render_logo_svg(size: int = 160) -> str:
    """Return a self-contained SVG string with a meander-band face logo.

    The outer edge of the band is a true radial-sinusoid meander — the same
    pattern the generator produces — so the logo visually matches the output.
    Two googly eyes and a smile peek out of the band's inner hole, and a few
    water bubbles drift around to keep the underwater-rugby vibe.
    """
    cx = cy = size / 2
    R_outer = size * 0.40      # band outer base radius
    A = size * 0.035           # wiggle amplitude
    f = 24                     # wiggle cycles around the band
    band_thickness = size * 0.08
    R_inner = R_outer - band_thickness
    N = 360                    # sample count around the circle

    # --- Meander outer edge --------------------------------------------------
    outer_pts = []
    for i in range(N):
        theta = 2.0 * math.pi * i / N
        r = R_outer + A * math.sin(f * theta)
        outer_pts.append(
            (cx + r * math.cos(theta), cy + r * math.sin(theta))
        )
    outer_path = (
        "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in outer_pts) + " Z"
    )

    # Inner edge: same wiggle, phase-shifted so the band looks like a proper
    # meander ribbon rather than a plain donut with a wavy crust.
    inner_pts = []
    for i in range(N):
        theta = 2.0 * math.pi * i / N
        r = R_inner + A * math.sin(f * theta)
        inner_pts.append(
            (cx + r * math.cos(theta), cy + r * math.sin(theta))
        )
    inner_path = (
        "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in inner_pts) + " Z"
    )

    band_path = outer_path + " " + inner_path

    # --- Googly eyes inside the hole -----------------------------------------
    eye_dx = R_inner * 0.45
    eye_y = cy - R_inner * 0.15
    eye_r = R_inner * 0.32
    pupil_r = eye_r * 0.45
    # Pupils offset slightly down-right so they look "googly"
    pupil_offset = pupil_r * 0.35

    # --- Smile ---------------------------------------------------------------
    smile_w = R_inner * 0.80
    smile_y = cy + R_inner * 0.35
    smile_d = (
        f"M {cx - smile_w / 2:.1f} {smile_y:.1f} "
        f"Q {cx:.1f} {smile_y + smile_w * 0.55:.1f} "
        f"{cx + smile_w / 2:.1f} {smile_y:.1f}"
    )

    # --- Bubbles -------------------------------------------------------------
    bubbles = [
        (size * 0.10, size * 0.18, size * 0.035, 0.75),
        (size * 0.88, size * 0.12, size * 0.025, 0.65),
        (size * 0.94, size * 0.55, size * 0.020, 0.55),
        (size * 0.08, size * 0.78, size * 0.028, 0.70),
        (size * 0.85, size * 0.90, size * 0.022, 0.65),
    ]
    bubble_svg = "".join(
        f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="{br:.1f}" '
        f'fill="#8ec5d4" opacity="{op}"/>'
        for bx, by, br, op in bubbles
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        f'role="img" aria-label="UWR Wristband logo">'
        f'{bubble_svg}'
        f'<path d="{band_path}" fill="#1f6feb" fill-rule="evenodd" '
        f'stroke="#0b2e5b" stroke-width="2" stroke-linejoin="round"/>'
        # Left eye
        f'<circle cx="{cx - eye_dx:.1f}" cy="{eye_y:.1f}" r="{eye_r:.1f}" '
        f'fill="#fff" stroke="#000" stroke-width="2"/>'
        f'<circle cx="{cx - eye_dx + pupil_offset:.1f}" '
        f'cy="{eye_y + pupil_offset:.1f}" r="{pupil_r:.1f}" fill="#000"/>'
        # Right eye
        f'<circle cx="{cx + eye_dx:.1f}" cy="{eye_y:.1f}" r="{eye_r:.1f}" '
        f'fill="#fff" stroke="#000" stroke-width="2"/>'
        f'<circle cx="{cx + eye_dx + pupil_offset:.1f}" '
        f'cy="{eye_y + pupil_offset:.1f}" r="{pupil_r:.1f}" fill="#000"/>'
        # Smile
        f'<path d="{smile_d}" stroke="#000" stroke-width="3" '
        f'fill="none" stroke-linecap="round"/>'
        f'</svg>'
    )
