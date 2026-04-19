"""UWR Wristband Generator — Streamlit app."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import streamlit as st

DOCS_DIR = Path(__file__).parent / "docs"

from uwr_wristband import APP_VERSION, GENERATOR_VERSION
from uwr_wristband.defaults import (
    DEFAULTS,
    MAX_CIRCUMFERENCE,
    MAX_TEXT_LENGTH,
    MIN_CIRCUMFERENCE,
    QUALITY_PRESETS,
    SIZE_PRESETS,
)
from uwr_wristband.generator import (
    assemble_grid_steps,
    build_params,
    generate_gcode_string,
)
from uwr_wristband.logo import render_logo_svg
from uwr_wristband.stl_export import generate_stl_export
from uwr_wristband.printers import (
    default_printer_index,
    get_all_printer_options,
    get_build_volume,
)
from uwr_wristband.visualization import generate_preview_figure

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="UWR Wristband Generator",
    page_icon=":ocean:",
    layout="wide",
)

_logo_col, _title_col = st.columns(
    [1, 10], vertical_alignment="center", gap="small"
)
with _logo_col:
    st.markdown(render_logo_svg(size=140), unsafe_allow_html=True)
with _title_col:
    st.title("UWR Wristband Generator")
    st.caption(
        "Generate custom G-code for 3D-printed underwater rugby wristbands. "
        "Adjust settings in the sidebar, then hit **Generate G-code**.  \n"
        f"App v{APP_VERSION} · Generator v{GENERATOR_VERSION}"
    )

st.info(
    "**New in v1.3.0:** Longer texts are now supported! Text is projected *around* "
    "the band (arc-length wrapping) instead of being flattened onto the front/back "
    "plane, so characters no longer get squished near the sides and can extend "
    "much further around the circumference.",
    icon="🆕",
)

st.info(
    "**New in v1.1.0:** STL export is now available! Generate an STL file for vase-mode slicing "
    "if your printer doesn't support raw G-code.",
    icon="🆕",
)

st.warning(
    "**Disclaimer:** Running generated G-code on your 3D printer is entirely at your own risk. "
    "Always review the G-code and verify printer settings before printing. "
    "Incorrect settings can damage your printer or cause a fire hazard. "
    "Make sure you understand what you are doing.",
    icon="⚠️",
)

# ---------------------------------------------------------------------------
# Printer options (cached)
# ---------------------------------------------------------------------------
printer_options = get_all_printer_options()
printer_labels = [p[0] for p in printer_options]
printer_name_map = {p[0]: p[1] for p in printer_options}

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "gcode" not in st.session_state:
    st.session_state.gcode = None
if "preview_fig" not in st.session_state:
    st.session_state.preview_fig = None
if "steps" not in st.session_state:
    st.session_state.steps = None
if "stl_data" not in st.session_state:
    st.session_state.stl_data = None
if "stl_filename" not in st.session_state:
    st.session_state.stl_filename = None
if "stl_mime" not in st.session_state:
    st.session_state.stl_mime = None

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Printer")
    printer_label = st.selectbox(
        "Printer model",
        printer_labels,
        index=default_printer_index(),
    )
    fc_printer_name = printer_name_map[printer_label]

    st.header("Band Defaults")
    st.caption("These are used as defaults for new rows in the band list.")
    text_front = st.text_input(
        "Front text (name / team)",
        value=DEFAULTS["text_front"],
        max_chars=MAX_TEXT_LENGTH,
    )
    text_back = st.text_input(
        "Back text (number)",
        value=DEFAULTS["text_back"],
        max_chars=MAX_TEXT_LENGTH,
    )

    size_labels = list(SIZE_PRESETS.keys())
    size_choice = st.selectbox("Wrist size", size_labels, index=2)  # default M
    if SIZE_PRESETS[size_choice] is None:
        circumference = st.number_input(
            "Custom circumference (mm)",
            min_value=MIN_CIRCUMFERENCE,
            max_value=MAX_CIRCUMFERENCE,
            value=DEFAULTS["circumference"],
            step=1.0,
            help=(
                "Inner circumference of the band in mm. Measure the wrist snugly "
                "and subtract ~10 mm — the TPU stretches slightly when worn."
            ),
        )
    else:
        circumference = SIZE_PRESETS[size_choice]

    # ---- Advanced settings ----
    show_advanced = st.checkbox("Show advanced settings")

    if show_advanced:
        st.subheader("Design Tuning")
        total_height = st.number_input(
            "Band height (mm)", 5.0, 40.0, DEFAULTS["total_height"], step=1.0,
            help="Total height (Z dimension) of the finished wristband.",
        )
        wiggle_amplitude = st.number_input(
            "Wiggle amplitude", 10.0, 100.0, DEFAULTS["wiggle_amplitude"], step=5.0,
            help=(
                "Radial amplitude of the meander pattern. Higher = deeper wiggle, "
                "more flex in the finished band but also more material."
            ),
        )
        wiggle_frequency = st.number_input(
            "Wiggle frequency", 20.0, 200.0, DEFAULTS["wiggle_frequency"], step=5.0,
            help=(
                "Number of wiggle cycles around the spiral. Higher = tighter, "
                "finer meander; lower = longer, smoother waves."
            ),
        )
        phase_shift_fraction = st.number_input(
            "Phase shift per layer (× wiggle wavelength)",
            -1.0,
            1.0,
            DEFAULTS["per_layer_phase_shift"] / (2.0 * math.pi),
            step=0.005,
            format="%.4f",
            help=(
                "How far the wiggle pattern is advanced between consecutive "
                "spiral turns, measured in units of the wiggle's own wavelength. "
                "0 = meanders stack (almost) vertically. ±0.5 = shifted by half a wiggle "
                "per layer (checkerboard look). ±1 = shifted by a full wavelength "
                "(visually identical to 0 for the wiggle itself). "
                "Non-zero values skew the meander pattern diagonally across "
                "the band — sign controls which way. Note: this is a *phase* "
                "shift, not the physical tilt angle of the meander columns; "
                "the visible slant also depends on circumference, wiggle "
                "frequency, and layer height."
            ),
        )
        per_layer_phase_shift = phase_shift_fraction * 2.0 * math.pi
        text_size = st.number_input(
            "Text size", 4.0, float(total_height), min(DEFAULTS["text_size"], float(total_height)), step=1.0,
            help="Approximate text character height in mm on the side of the band. Capped at band height.",
        )
        text_emboss_factor = st.number_input(
            "Text emboss factor",
            1.0,
            3.0,
            DEFAULTS["text_emboss_factor"],
            step=0.1,
            format="%.2f",
            help=(
                "Multiplier on the wiggle amplitude at text points — controls how "
                "far the text stands out from the band. 1.0 = flush, 1.5 = default, "
                "higher = more pronounced relief."
            ),
        )
        text_vertical_offset = st.number_input(
            "Text vertical offset (mm)",
            -float(total_height) / 2.0,
            float(total_height) / 2.0,
            float(DEFAULTS["text_vertical_offset"]),
            step=0.5,
            format="%.1f",
            help=(
                "Shift text up (+) or down (-) from the vertical center of the "
                "band. 0 = centered."
            ),
        )

        st.subheader("Quality")
        quality_labels = list(QUALITY_PRESETS.keys())
        quality_choice = st.selectbox(
            "Point density", quality_labels, index=1,
            help=(
                "Number of points sampled per spiral. Higher density = smoother "
                "curves but slower generation and larger G-code / STL files."
            ),
        )
        num_points = QUALITY_PRESETS[quality_choice]
    
        st.subheader("Print Settings")
        st.caption(
            "These settings are baked into the **G-code only**. They have no "
            "effect on STL export — configure those in your slicer instead."
        )
        nozzle_temp = st.number_input(
            "Nozzle temp (C)", 180, 280, DEFAULTS["nozzle_temp"],
            help="**G-code only.** Hotend temperature. 220 °C is a good TPU starting point; try ~210 °C for softer TPU.",
        )
        bed_temp = st.number_input(
            "Bed temp (C)", 0, 120, DEFAULTS["bed_temp"],
            help="**G-code only.** Heated-bed temperature. 60 °C works well for TPU on PEI / glass.",
        )
        print_speed = st.number_input(
            "Print speed (mm/min)", 300, 3000, DEFAULTS["print_speed"], step=100,
            help=(
                "**G-code only.** Main travel-over-material speed. 1100 mm/min (~18 mm/s) "
                "is a safe TPU default — Bowden extruders may need slower."
            ),
        )
        fan_percent = st.slider(
            "Fan %", 0, 100, DEFAULTS["fan_percent"],
            help="**G-code only.** Part-cooling fan duty cycle during printing.",
        )
        EW = st.number_input(
            "Extrusion width (mm)", 0.2, 1.2, DEFAULTS["EW"], step=0.05, format="%.2f",
            help=(
                "**G-code only.** Width of a single extruded line. Typically matches or slightly "
                "exceeds the nozzle diameter (0.4 mm nozzle → 0.4–0.5 mm)."
            ),
        )
        EH = st.number_input(
            "Layer height (mm)", 0.05, 0.4, DEFAULTS["EH"], step=0.05, format="%.2f",
            help=(
                "**G-code only.** Height of each printed layer / spiral pitch. 0.2 mm is the standard "
                "default for TPU and also the recommended setting for STL vase mode."
            ),
        )
        ease_in_height = st.number_input(
            "Ease-in height (mm)",
            0.0,
            5.0,
            DEFAULTS["ease_in_height"],
            step=0.2,
            format="%.1f",
            help=(
                "**G-code only.** Bottom region (in mm) where the extrusion width "
                "ramps up from reduced → full. Gives the first layers a thinner start. "
                "(Has no effect on STL geometry — the slicer "
                "controls first-layer width there.)"
            ),
        )
        ease_out_height = st.number_input(
            "Ease-out height (mm)",
            0.0,
            5.0,
            DEFAULTS["ease_out_height"],
            step=0.2,
            format="%.1f",
            help=(
                "**G-code only.** Top region (in mm) where the extrusion width "
                "ramps back down, giving the band a cleaner, rounder finishing edge."
            ),
        )
        ease_strength = st.slider(
            "Ease strength", 0.0, 1.0, DEFAULTS["ease_strength"], step=0.05,
            help=(
                "**G-code only.** How strongly the extrusion width is attenuated "
                "in the ease-in/out regions. 0 = full width everywhere, 1 = width "
                "tapers to zero at the very ends."
            ),
        )
        
    else:
        nozzle_temp = DEFAULTS["nozzle_temp"]
        bed_temp = DEFAULTS["bed_temp"]
        print_speed = DEFAULTS["print_speed"]
        fan_percent = DEFAULTS["fan_percent"]
        EW = DEFAULTS["EW"]
        EH = DEFAULTS["EH"]
        total_height = DEFAULTS["total_height"]
        wiggle_amplitude = DEFAULTS["wiggle_amplitude"]
        wiggle_frequency = DEFAULTS["wiggle_frequency"]
        per_layer_phase_shift = DEFAULTS["per_layer_phase_shift"]
        text_size = DEFAULTS["text_size"]
        text_emboss_factor = DEFAULTS["text_emboss_factor"]
        text_vertical_offset = DEFAULTS["text_vertical_offset"]
        num_points = DEFAULTS["num_points_per_spiral"]
        ease_in_height = DEFAULTS["ease_in_height"]
        ease_out_height = DEFAULTS["ease_out_height"]
        ease_strength = DEFAULTS["ease_strength"]

# ---------------------------------------------------------------------------
# Grid layout + band list (main area, above generate buttons)
# ---------------------------------------------------------------------------
st.header("Bands")

grid_col1, grid_col2, grid_col3, grid_col4 = st.columns(4)
with grid_col1:
    grid_nx = st.number_input(
        "Columns", min_value=1, max_value=5, value=1,
        help="Number of bands along the X axis of the build plate.",
    )
with grid_col2:
    grid_ny = st.number_input(
        "Rows", min_value=1, max_value=5, value=1,
        help="Number of bands along the Y axis of the build plate.",
    )
with grid_col3:
    grid_spacing_x = st.number_input(
        "X spacing (mm)", min_value=50.0, max_value=200.0, value=90.0, step=5.0,
        help=(
            "Center-to-center distance between bands along X. TPU is soft enough "
            "that you can push this tighter than the band diameter — the head "
            "will just nudge already-printed bands aside."
        ),
    )
with grid_col4:
    grid_spacing_y = st.number_input(
        "Y spacing (mm)", min_value=50.0, max_value=200.0, value=86.0, step=5.0,
        help="Center-to-center distance between bands along Y.",
    )

num_slots = grid_nx * grid_ny

# Build default dataframe for the band list
default_data = {
    "Enabled": [True] * num_slots,
    "Front Text": [text_front] * num_slots,
    "Back Text": [text_back] * num_slots,
    "Circumference (mm)": [circumference] * num_slots,
}
default_df = pd.DataFrame(default_data)
default_df.index = range(1, num_slots + 1)
default_df.index.name = "#"

st.caption(
    f"Grid: **{grid_nx} x {grid_ny}** = {num_slots} slots. "
    "Uncheck **Enabled** to skip a slot. Texts can be left blank."
)

band_df = st.data_editor(
    default_df,
    width="stretch",
    num_rows="fixed",
    key="band_table",
    column_config={
        "Enabled": st.column_config.CheckboxColumn(
            default=True,
        ),
        "Front Text": st.column_config.TextColumn(
            max_chars=MAX_TEXT_LENGTH,
        ),
        "Back Text": st.column_config.TextColumn(
            max_chars=MAX_TEXT_LENGTH,
        ),
        "Circumference (mm)": st.column_config.NumberColumn(
            min_value=MIN_CIRCUMFERENCE,
            max_value=MAX_CIRCUMFERENCE,
            step=1.0,
            format="%.0f",
        ),
    },
)

# Convert dataframe to spiral_configs (None for disabled rows)
spiral_configs = []
for _, row in band_df.iterrows():
    enabled = bool(row["Enabled"]) if pd.notna(row["Enabled"]) else True
    if not enabled:
        spiral_configs.append(None)
        continue
    front = str(row["Front Text"]).strip() if pd.notna(row["Front Text"]) else ""
    back = str(row["Back Text"]).strip() if pd.notna(row["Back Text"]) else ""
    circ = float(row["Circumference (mm)"]) if pd.notna(row["Circumference (mm)"]) else circumference
    spiral_configs.append(
        {"text_front": front, "text_back": back, "circumference": circ}
    )

num_active = sum(1 for c in spiral_configs if c is not None)

# ---------------------------------------------------------------------------
# Build volume check
# ---------------------------------------------------------------------------
vol_x, vol_y, vol_z = get_build_volume(fc_printer_name)

# Estimate grid footprint (conservative: use largest circumference radius)
active_circs = [
    c["circumference"] for c in spiral_configs if c is not None
]
if active_circs:
    max_radius = max(active_circs) / (2.0 * math.pi)
else:
    max_radius = circumference / (2.0 * math.pi)

# Rough band diameter on the print bed (radius + wiggle amplitude contribution)
band_diameter = 2 * (max_radius + wiggle_amplitude * 0.02)  # wiggle is cumulative, rough est.

first_center_x = 40.0
first_center_y = 48.0

if num_active <= 1:
    footprint_x = band_diameter
    footprint_y = band_diameter
else:
    footprint_x = first_center_x + (grid_nx - 1) * grid_spacing_x + band_diameter / 2
    footprint_y = first_center_y + (grid_ny - 1) * grid_spacing_y + band_diameter / 2

if num_active > 0 and (footprint_x > vol_x or footprint_y > vol_y):
    st.warning(
        f"Grid footprint (~{footprint_x:.0f} x {footprint_y:.0f} mm) "
        f"may exceed printer build area "
        f"({vol_x:.0f} x {vol_y:.0f} mm). "
        f"Bands may be clipped or fail to print."
    )

if num_active == 0:
    st.info("No bands configured. Enable at least one row in the table above.")

# ---------------------------------------------------------------------------
# Build params
# ---------------------------------------------------------------------------
params = build_params(
    text_front=text_front,
    text_back=text_back,
    circumference=circumference,
    printer_name=fc_printer_name,
    nozzle_temp=nozzle_temp,
    bed_temp=bed_temp,
    print_speed=print_speed,
    fan_percent=fan_percent,
    EW=EW,
    EH=EH,
    total_height=total_height,
    wiggle_amplitude=wiggle_amplitude,
    wiggle_frequency=wiggle_frequency,
    per_layer_phase_shift=per_layer_phase_shift,
    text_size=text_size,
    text_emboss_factor=text_emboss_factor,
    text_vertical_offset=text_vertical_offset,
    ease_in_height=ease_in_height,
    ease_out_height=ease_out_height,
    ease_strength=ease_strength,
    num_points_per_spiral=num_points,
    grid_nx=grid_nx,
    grid_ny=grid_ny,
    grid_spacing_x=grid_spacing_x,
    grid_spacing_y=grid_spacing_y,
    spiral_configs=spiral_configs,
)

# ---------------------------------------------------------------------------
# Main area — generate / preview / download
# ---------------------------------------------------------------------------
col_left, col_right = st.columns([3, 2])

with col_left:
    generate_btn = st.button(
        "Generate G-code",
        type="primary",
        width="stretch",
        disabled=num_active == 0,
    )
    preview_btn = st.button(
        "Show 3D Preview",
        width="stretch",
        disabled=num_active == 0,
    )
    stl_btn = st.button(
        "Generate STL",
        width="stretch",
        disabled=num_active == 0,
    )

    if generate_btn:
        st.session_state.gcode = None
        st.session_state.preview_fig = None
        st.session_state.steps = None

        progress = st.progress(0, text="Generating wristband...")

        def _update_progress(current: int, total: int) -> None:
            progress.progress(
                current / total,
                text=f"Generating band {current} of {total}...",
            )

        try:
            steps = assemble_grid_steps(params, progress_callback=_update_progress)
            st.session_state.steps = steps
            progress.progress(1.0, text="Building G-code...")
            gcode = generate_gcode_string(params)
            st.session_state.gcode = gcode
            progress.empty()
            st.success(
                f"G-code generated ({len(gcode) / 1024:.0f} KB, "
                f"{num_active} band{'s' if num_active != 1 else ''}). "
                "Click **Download** below."
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Generation failed: {exc}")
            with st.expander("Details"):
                st.exception(exc)

    if preview_btn:
        if st.session_state.steps is None:
            st.session_state.preview_fig = None

            progress = st.progress(0, text="Generating preview...")

            def _update_preview(current: int, total: int) -> None:
                progress.progress(
                    current / total,
                    text=f"Generating band {current} of {total}...",
                )

            try:
                steps = assemble_grid_steps(
                    params, progress_callback=_update_preview
                )
                st.session_state.steps = steps
                progress.progress(1.0, text="Rendering preview...")
                fig = generate_preview_figure(steps, EW=EW, EH=EH)
                st.session_state.preview_fig = fig
                progress.empty()
            except Exception as exc:
                progress.empty()
                st.error(f"Preview failed: {exc}")
                with st.expander("Details"):
                    st.exception(exc)
        else:
            with st.spinner("Rendering preview..."):
                try:
                    fig = generate_preview_figure(
                        st.session_state.steps, EW=EW, EH=EH
                    )
                    st.session_state.preview_fig = fig
                except Exception as exc:
                    st.error(f"Preview failed: {exc}")
                    with st.expander("Details"):
                        st.exception(exc)

    if stl_btn:
        st.session_state.stl_data = None

        progress = st.progress(0, text="Generating STL...")

        def _update_stl(current: int, total: int) -> None:
            progress.progress(
                current / total,
                text=f"Generating band {current} of {total}...",
            )

        try:
            stl_bytes, stl_name, stl_mime = generate_stl_export(
                params, stride=1, progress_callback=_update_stl
            )
            st.session_state.stl_data = stl_bytes
            st.session_state.stl_filename = stl_name
            st.session_state.stl_mime = stl_mime
            progress.empty()
            st.success(
                f"STL generated ({len(stl_bytes) / 1024:.0f} KB, "
                f"{num_active} band{'s' if num_active != 1 else ''}). "
                "Click **Download** below."
            )
        except Exception as exc:
            progress.empty()
            st.error(f"STL generation failed: {exc}")
            with st.expander("Details"):
                st.exception(exc)

    if st.session_state.gcode is not None:
        filename = f"uwr_wristband_{text_front}_{text_back}.gcode"
        st.download_button(
            "Download .gcode",
            data=st.session_state.gcode,
            file_name=filename,
            mime="text/plain",
            width="stretch",
        )

    if st.session_state.stl_data is not None:
        st.download_button(
            "Download .stl" if st.session_state.stl_mime == "application/sla" else "Download .zip (STL)",
            data=st.session_state.stl_data,
            file_name=st.session_state.stl_filename,
            mime=st.session_state.stl_mime,
            width="stretch",
        )

with col_right:
    if st.session_state.preview_fig is not None:
        st.plotly_chart(
            st.session_state.preview_fig, width="stretch"
        )
    else:
        st.info("Click **Show 3D Preview** to see the wristband model.")

# ---------------------------------------------------------------------------
# What is UWR?
# ---------------------------------------------------------------------------
with st.expander("What is UWR?"):
    st.markdown(
        "Underwater rugby (UWR) is a fast-paced team sport played in a deep pool. "
        "Two teams of six try to get a saltwater-filled ball into a basket at the "
        "bottom of the opposing end. It's fully three-dimensional — players dive, "
        "pass, and tackle underwater while holding their breath. Wristbands help "
        "identify players and their respective team (white or blue/black) during "
        "the game.\n\n"
        "[Watch UWR in action](https://youtu.be/dx4tbtoWzvA?si=hUjfREuN5V7mm_EU)"
    )

# ---------------------------------------------------------------------------
# Printing tips
# ---------------------------------------------------------------------------
with st.expander("Printing Tips — G-code"):
    st.markdown((DOCS_DIR / "tips_gcode.md").read_text(encoding="utf-8"))

with st.expander("Printing Tips — STL (vase mode)"):
    st.markdown((DOCS_DIR / "tips_stl.md").read_text(encoding="utf-8"))

# ---------------------------------------------------------------------------
# Acknowledgements
# ---------------------------------------------------------------------------
with st.expander("Acknowledgements"):
    st.markdown(
        "The meander pattern used in the wristband generation is based on the paper "
        "[*River meanders — Theory of minimum variance*](https://pubs.usgs.gov/publication/pp422H) "
        "by Langbein & Leopold (1966). The mathematical model of natural river meandering "
        "provided the foundation for the spiral-wiggle geometry that gives the bands "
        "their flexibility and distinctive look.\n\n"
        "The Streamlit app, project structure, and UI wiring were vibecoded with the help of "
        "Claude Code. However, the core wristband generation logic — the spiral-meander math, "
        "text polygon projection, ease-in/out curves, grid assembly, and the fullcontrol "
        "integration — was designed, tested, and iterated on by hand over multiple "
        "print cycles. The geometry had to be right to produce bands that actually print well, "
        "flex correctly, and feel good on a wrist. AI helped scaffold the webapp; the engineering "
        "behind the G-code is human. I have printed at least >100 bands during the making of this code. "
        "'Why?' you ask? It was just a dumb idea in the beginning, but it turned into a fun side quest. "
        "And now here we are..."
    )
