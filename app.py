"""UWR Wristband Generator — Streamlit app."""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from uwr_wristband import APP_VERSION, BAND_VERSION
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

st.title("UWR Wristband Generator")
st.caption(
    "Generate custom G-code for 3D-printed underwater rugby wristbands. "
    "Adjust settings in the sidebar, then hit **Generate G-code**.  \n"
    f"App v{APP_VERSION} · Band v{BAND_VERSION}"
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
            step=5.0,
        )
    else:
        circumference = SIZE_PRESETS[size_choice]

    # ---- Advanced settings ----
    show_advanced = st.checkbox("Show advanced settings")

    if show_advanced:
        st.subheader("Print Settings")
        nozzle_temp = st.number_input(
            "Nozzle temp (C)", 180, 280, DEFAULTS["nozzle_temp"]
        )
        bed_temp = st.number_input("Bed temp (C)", 0, 120, DEFAULTS["bed_temp"])
        print_speed = st.number_input(
            "Print speed (mm/min)", 300, 3000, DEFAULTS["print_speed"], step=100
        )
        fan_percent = st.slider("Fan %", 0, 100, DEFAULTS["fan_percent"])
        EW = st.number_input(
            "Extrusion width (mm)", 0.2, 1.2, DEFAULTS["EW"], step=0.05, format="%.2f"
        )
        EH = st.number_input(
            "Layer height (mm)", 0.05, 0.4, DEFAULTS["EH"], step=0.05, format="%.2f"
        )
        total_height = st.number_input(
            "Band height (mm)", 5.0, 40.0, DEFAULTS["total_height"], step=1.0
        )

        st.subheader("Design Tuning")
        wiggle_amplitude = st.number_input(
            "Wiggle amplitude", 10.0, 200.0, DEFAULTS["wiggle_amplitude"], step=5.0
        )
        wiggle_frequency = st.number_input(
            "Wiggle frequency", 20.0, 200.0, DEFAULTS["wiggle_frequency"], step=5.0
        )
        text_size = st.number_input(
            "Text size", 4.0, 20.0, DEFAULTS["text_size"], step=1.0
        )

        st.subheader("Quality")
        quality_labels = list(QUALITY_PRESETS.keys())
        quality_choice = st.selectbox("Point density", quality_labels, index=1)
        num_points = QUALITY_PRESETS[quality_choice]

        ease_in_height = st.number_input(
            "Ease-in height (mm)",
            0.0,
            5.0,
            DEFAULTS["ease_in_height"],
            step=0.2,
            format="%.1f",
        )
        ease_out_height = st.number_input(
            "Ease-out height (mm)",
            0.0,
            5.0,
            DEFAULTS["ease_out_height"],
            step=0.2,
            format="%.1f",
        )
        ease_strength = st.slider(
            "Ease strength", 0.0, 1.0, DEFAULTS["ease_strength"], step=0.05
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
        text_size = DEFAULTS["text_size"]
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
    grid_nx = st.number_input("Columns", min_value=1, max_value=5, value=1)
with grid_col2:
    grid_ny = st.number_input("Rows", min_value=1, max_value=5, value=1)
with grid_col3:
    grid_spacing_x = st.number_input(
        "X spacing (mm)", min_value=50.0, max_value=200.0, value=90.0, step=5.0
    )
with grid_col4:
    grid_spacing_y = st.number_input(
        "Y spacing (mm)", min_value=50.0, max_value=200.0, value=86.0, step=5.0
    )

num_slots = grid_nx * grid_ny

# Build default dataframe for the band list
default_data = {
    "Front Text": [text_front] * num_slots,
    "Back Text": [text_back] * num_slots,
    "Circumference (mm)": [circumference] * num_slots,
}
default_df = pd.DataFrame(default_data)
default_df.index = range(1, num_slots + 1)
default_df.index.name = "#"

st.caption(
    f"Grid: **{grid_nx} x {grid_ny}** = {num_slots} slots. "
    "Clear the Front Text to leave a slot empty."
)

band_df = st.data_editor(
    default_df,
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "Front Text": st.column_config.TextColumn(
            max_chars=MAX_TEXT_LENGTH,
        ),
        "Back Text": st.column_config.TextColumn(
            max_chars=MAX_TEXT_LENGTH,
        ),
        "Circumference (mm)": st.column_config.NumberColumn(
            min_value=MIN_CIRCUMFERENCE,
            max_value=MAX_CIRCUMFERENCE,
            step=5.0,
            format="%.0f",
        ),
    },
)

# Convert dataframe to spiral_configs (None for empty rows)
spiral_configs = []
for _, row in band_df.iterrows():
    front = str(row["Front Text"]).strip() if pd.notna(row["Front Text"]) else ""
    back = str(row["Back Text"]).strip() if pd.notna(row["Back Text"]) else ""
    circ = float(row["Circumference (mm)"]) if pd.notna(row["Circumference (mm)"]) else circumference
    if front:
        spiral_configs.append(
            {"text_front": front, "text_back": back, "circumference": circ}
        )
    else:
        spiral_configs.append(None)

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
    st.info("No bands configured. Fill in the Front Text for at least one row.")

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
    text_size=text_size,
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
        use_container_width=True,
        disabled=num_active == 0,
    )
    preview_btn = st.button(
        "Show 3D Preview",
        use_container_width=True,
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

    if st.session_state.gcode is not None:
        filename = f"uwr_wristband_{text_front}_{text_back}.gcode"
        st.download_button(
            "Download .gcode",
            data=st.session_state.gcode,
            file_name=filename,
            mime="text/plain",
            use_container_width=True,
        )

with col_right:
    if st.session_state.preview_fig is not None:
        st.plotly_chart(
            st.session_state.preview_fig, use_container_width=True
        )
    else:
        st.info("Click **Show 3D Preview** to see the wristband model.")

# ---------------------------------------------------------------------------
# Printing tips
# ---------------------------------------------------------------------------
with st.expander("Printing Tips"):
    st.markdown(
        """\
**Measuring your wrist:** Wrap a tape measure snugly around the wrist and note the
circumference in mm. The band stretches slightly, so a snug fit is fine. Currently
would recommend to deduct 10 mm.

**Material:** Use TPU (flexible filament). 95A is just fine. Softer ones might be
smoother but are more expensive and more difficult to print.

**Bed adhesion:** TPU sticks well to PEI and glass beds.

**First layer:** Print slowly (~50 % speed) for good adhesion. The default ease-in
settings handle this.

**Temperatures:** Defaults are nozzle 220 °C / bed 60 °C. Lower to ~210 °C for
softer TPU.

**Speed:** TPU prints best at moderate speeds. The default 1100 mm/min (~18 mm/s)
is a safe starting point. Bowden extruders may need slower.

**Removing from bed:** Let the print cool fully before removing — TPU peels off
easily once cool.

**Multi-band prints:** Check that all bands fit on your printer's bed. The app warns
you if the grid footprint exceeds the build area. But you can indeed push the limits
with the spacing (because we are dealing with TPU here). So although the print head
might collide with an already printed band it pushes the old one aside with ease.
That way you can easily fit 3x3 bands on a 250x250 build plate.
"""
    )
