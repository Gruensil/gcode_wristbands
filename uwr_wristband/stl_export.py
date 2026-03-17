"""STL export — build a solid cylindrical mesh from the spiral path.

The spiral path points are split into rows by turn (sequential point
index, not angle) so the full meander geometry is preserved exactly.
Each turn is one mesh row; adjacent rows are connected with quads.
Flat disc caps close the top and bottom for a watertight solid.
"""

from __future__ import annotations

import io
import math
import struct
import zipfile
from typing import Callable, List, Optional, Tuple

import numpy as np

from .generator import generate_band_arrays


# ---------------------------------------------------------------------------
# Width profile (vectorised ease-in/out)
# ---------------------------------------------------------------------------

def compute_width_profile(
    z_vals: np.ndarray,
    EW: float,
    initial_z: float,
    total_height: float,
    ease_in_height: float,
    ease_out_height: float,
    ease_strength: float,
) -> np.ndarray:
    """Return per-point extrusion widths with ease-in/out scaling."""
    usable_height = float(z_vals.max())
    rel_z = np.clip(z_vals - initial_z, 0.0, usable_height)

    widths = np.full_like(rel_z, EW)

    if ease_in_height > 0:
        mask = rel_z < ease_in_height
        t = rel_z[mask] / ease_in_height
        ease_val = 0.5 * (1.0 - np.cos(np.pi * t))
        widths[mask] = EW * (1.0 - ease_strength + ease_strength * ease_val)

    if ease_out_height > 0:
        mask = rel_z > (usable_height - ease_out_height)
        dist = usable_height - rel_z[mask]
        t = dist / ease_out_height
        ease_val = 0.5 * (1.0 - np.cos(np.pi * t))
        widths[mask] = EW * (1.0 - ease_strength + ease_strength * ease_val)

    return widths


# ---------------------------------------------------------------------------
# Mesh construction — solid cylinder from sequential spiral points
# ---------------------------------------------------------------------------

def build_solid_mesh(
    points: np.ndarray,
    widths: np.ndarray,
    EH: float,
    center_xy: Tuple[float, float],
    num_turns: int,
    wiggle_frequency: float = 80.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Build a fully solid mesh from the spiral path.

    The spiral points are split into rows by sequential index (one row
    per revolution).  This preserves the full meander pattern — no
    angle-based resampling that would destroy the wiggle geometry.

    The outer surface is offset radially by EW/2.  Flat disc caps close
    the top and bottom.

    Returns ``(triangles, normals)`` where *triangles* is ``(M, 3, 3)``
    and *normals* is ``(M, 3)``.
    """
    cx, cy = center_xy
    n_pts = len(points)

    # Split the sequential spiral points into rows of equal length.
    # Each row = one revolution of the spiral.
    pts_per_turn = n_pts // num_turns
    if pts_per_turn < 10:
        pts_per_turn = n_pts // max(num_turns // 2, 1)

    # Trim to exact multiple
    usable = pts_per_turn * num_turns
    if usable > n_pts:
        num_turns = n_pts // pts_per_turn
        usable = pts_per_turn * num_turns

    grid = points[:usable].reshape(num_turns, pts_per_turn, 3).copy()

    # Compute radii and angles for radial offset
    grid_dx = grid[:, :, 0] - cx
    grid_dy = grid[:, :, 1] - cy
    grid_radii = np.sqrt(grid_dx ** 2 + grid_dy ** 2)
    grid_angles = np.arctan2(grid_dy, grid_dx)

    # Width profile: interpolate from the original widths by z
    z_spiral = points[:usable, 2]
    w_usable = widths[:usable]
    z_order = np.argsort(z_spiral)
    z_sorted = z_spiral[z_order]
    w_sorted = w_usable[z_order]

    # Per-row average z for width lookup
    z_per_row = grid[:, :, 2].mean(axis=1)
    layer_widths = np.interp(z_per_row, z_sorted, w_sorted)

    # Use the spiral path directly as the STL surface — no radial offset.
    outer = grid.copy()

    rows, cols = num_turns, pts_per_turn

    # ----- Outer wall faces -----
    # Connect adjacent turns with quads.  Column wrapping connects the
    # last point of a turn to the first point of the same turn — this
    # creates a tiny Z-step (one spiral_layer_thickness ≈ 0.2 mm) which
    # is invisible in the final mesh.
    r_idx = np.arange(rows - 1)
    c_idx = np.arange(cols)
    rr, cc = np.meshgrid(r_idx, c_idx, indexing="ij")
    cc_next = (cc + 1) % cols

    p00 = outer[rr, cc]
    p01 = outer[rr, cc_next]
    p10 = outer[rr + 1, cc]
    p11 = outer[rr + 1, cc_next]

    num_quads = (rows - 1) * cols
    wall_tris = np.empty((num_quads * 2, 3, 3), dtype=np.float32)

    flat_p00 = p00.reshape(-1, 3)
    flat_p01 = p01.reshape(-1, 3)
    flat_p10 = p10.reshape(-1, 3)
    flat_p11 = p11.reshape(-1, 3)

    wall_tris[0::2, 0] = flat_p00
    wall_tris[0::2, 1] = flat_p01
    wall_tris[0::2, 2] = flat_p10
    wall_tris[1::2, 0] = flat_p01
    wall_tris[1::2, 1] = flat_p11
    wall_tris[1::2, 2] = flat_p10

    # ----- Flat disc caps -----
    def _disc_cap(ring, center_z, flip=False):
        """Fan-triangulate a flat disc at *center_z*."""
        n = len(ring)
        c_idx = np.arange(n)
        c_next = (c_idx + 1) % n
        tris = np.empty((n, 3, 3), dtype=np.float32)
        center_3d = np.array([cx, cy, center_z], dtype=np.float32)
        center_rep = np.broadcast_to(center_3d, (n, 3))

        # Project ring onto flat z
        flat_ring = ring.copy().astype(np.float32)
        flat_ring[:, 2] = center_z

        if flip:
            tris[:, 0] = center_rep
            tris[:, 1] = flat_ring[c_next]
            tris[:, 2] = flat_ring[c_idx]
        else:
            tris[:, 0] = center_rep
            tris[:, 1] = flat_ring[c_idx]
            tris[:, 2] = flat_ring[c_next]
        return tris

    def _transition_strip(ring, flat_z, flip=False):
        """Strip connecting the helical ring to the flat cap Z."""
        n = len(ring)
        c_idx = np.arange(n)
        c_next = (c_idx + 1) % n
        tris = np.empty((n * 2, 3, 3), dtype=np.float32)

        flat_ring = ring.copy().astype(np.float32)
        flat_ring[:, 2] = flat_z
        actual = ring.astype(np.float32)

        if flip:
            tris[0::2, 0] = flat_ring[c_idx]
            tris[0::2, 1] = flat_ring[c_next]
            tris[0::2, 2] = actual[c_idx]
            tris[1::2, 0] = flat_ring[c_next]
            tris[1::2, 1] = actual[c_next]
            tris[1::2, 2] = actual[c_idx]
        else:
            tris[0::2, 0] = actual[c_idx]
            tris[0::2, 1] = actual[c_next]
            tris[0::2, 2] = flat_ring[c_idx]
            tris[1::2, 0] = actual[c_next]
            tris[1::2, 1] = flat_ring[c_next]
            tris[1::2, 2] = flat_ring[c_idx]
        return tris

    bottom_z = float(outer[:, :, 2].min())
    top_z = float(outer[:, :, 2].max())

    bottom_strip = _transition_strip(outer[0], bottom_z, flip=True)
    bottom_cap = _disc_cap(outer[0], bottom_z, flip=True)
    top_strip = _transition_strip(outer[-1], top_z, flip=False)
    top_cap = _disc_cap(outer[-1], top_z, flip=False)

    # ----- Combine -----
    all_tris = np.concatenate(
        [wall_tris, bottom_strip, bottom_cap, top_strip, top_cap], axis=0
    )

    # ----- Face normals -----
    v0 = all_tris[:, 1] - all_tris[:, 0]
    v1 = all_tris[:, 2] - all_tris[:, 0]
    face_normals = np.cross(v0, v1)
    fn_norms = np.linalg.norm(face_normals, axis=1, keepdims=True)
    fn_norms = np.where(fn_norms < 1e-12, 1.0, fn_norms)
    face_normals = face_normals / fn_norms

    return all_tris, face_normals


# ---------------------------------------------------------------------------
# Binary STL writing (fast, vectorised)
# ---------------------------------------------------------------------------

def _write_binary_stl_fast(triangles: np.ndarray, normals: np.ndarray) -> bytes:
    """Vectorised binary STL writer using numpy structured array."""
    num_tris = len(triangles)
    record_dtype = np.dtype([
        ("normal", "<f4", (3,)),
        ("v0", "<f4", (3,)),
        ("v1", "<f4", (3,)),
        ("v2", "<f4", (3,)),
        ("attr", "<u2"),
    ])
    records = np.zeros(num_tris, dtype=record_dtype)
    records["normal"] = normals.astype(np.float32)
    records["v0"] = triangles[:, 0].astype(np.float32)
    records["v1"] = triangles[:, 1].astype(np.float32)
    records["v2"] = triangles[:, 2].astype(np.float32)

    buf = io.BytesIO()
    header = b"UWR Wristband Generator STL" + b"\x00" * 53
    buf.write(header[:80])
    buf.write(struct.pack("<I", num_tris))
    buf.write(records.tobytes())
    return buf.getvalue()


# ---------------------------------------------------------------------------
# High-level export
# ---------------------------------------------------------------------------

def generate_stl_export(
    params: dict,
    stride: int = 1,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple[bytes, str, str]:
    """Generate STL file(s) from params.

    Returns ``(file_bytes, filename, mime_type)``.
    Single band  -> raw ``.stl`` bytes.
    Multiple bands -> ``.zip`` containing one STL per band.
    """
    band_data = generate_band_arrays(params, progress_callback=progress_callback)

    EW = params["EW"]
    EH = params["EH"]
    initial_z = params["initial_z"]
    total_height = params["total_height"]
    ease_in_height = params["ease_in_height"]
    ease_out_height = params["ease_out_height"]
    ease_strength = params["ease_strength"]
    spiral_layer_thickness = params["spiral_layer_thickness"]
    wiggle_frequency = params.get("wiggle_frequency", 80.0)

    num_turns = max(2, int(total_height / spiral_layer_thickness))

    stl_files: List[Tuple[str, bytes]] = []

    for i, (points, center_xy, config) in enumerate(band_data):
        # No downsampling — we need all points to preserve meander detail
        if stride > 1:
            indices = np.arange(0, len(points), stride)
            if indices[-1] != len(points) - 1:
                indices = np.append(indices, len(points) - 1)
            ds_points = points[indices]
        else:
            ds_points = points

        # Width profile
        widths = compute_width_profile(
            ds_points[:, 2], EW, initial_z, total_height,
            ease_in_height, ease_out_height, ease_strength,
        )

        # Build solid mesh
        triangles, normals = build_solid_mesh(
            ds_points, widths, EH, center_xy, num_turns, wiggle_frequency
        )

        # Write STL
        stl_bytes = _write_binary_stl_fast(triangles, normals)

        front = config.get("text_front", "band")
        back = config.get("text_back", "")
        name_parts = [f"band_{i + 1}"]
        if front:
            name_parts.append(front)
        if back:
            name_parts.append(str(back))
        filename = "_".join(name_parts) + ".stl"
        filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)

        stl_files.append((filename, stl_bytes))

    if len(stl_files) == 1:
        return stl_files[0][1], stl_files[0][0], "application/sla"

    # Multiple bands -> ZIP
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in stl_files:
            zf.writestr(name, data)
    return zip_buf.getvalue(), "uwr_wristbands.zip", "application/zip"
