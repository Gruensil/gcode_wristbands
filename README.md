# UWR Wristband Generator

A Streamlit web app for generating G-code for 3D-printed wristbands. Originally designed for underwater rugby (UWR) player identification, but suitable for any custom text wristband.

Each wristband is printed as a single continuous spiral with embossed text on the front and back. The spiral-meander pattern gives the bands flexibility and a distinctive look.

## Features

- **Custom text** — set front text (name/team) and back text (number) per band
- **Size presets** — XS through XL wrist sizes, or enter a custom circumference
- **Multi-band printing** — generate a grid of up to 5x5 bands in a single print job, each with individual text and size
- **675+ printer profiles** — 12 community-tested profiles and 663 Cura profiles with automatic build volume detection
- **Build area warning** — alerts you if the grid layout exceeds your printer's bed size
- **3D preview** — interactive plotly visualization before committing to a print
- **Advanced tuning** — nozzle/bed temp, print speed, wiggle pattern, text size, ease-in/out, quality presets

## Quick Start

```bash
# Clone the repo
git clone https://github.com/gruensil/gcode_wristbands.git
cd uwr_wristband

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

The app opens in your browser at `http://localhost:8501`.

## Requirements

- Python 3.10+
- [fullcontrol](https://github.com/FullControlXYZ/fullcontrol) (G-code generation library)
- Streamlit, NumPy, Matplotlib, Shapely 2.0+, Plotly

All dependencies are listed in `requirements.txt`.

## Usage

1. **Select your printer** in the sidebar (default: Prusa MK4)
2. **Set band defaults** — front/back text, wrist size
3. **Configure the grid** — set columns and rows, then edit individual bands in the table (clear front text to skip a slot)
4. **Click "Generate G-code"** — download the `.gcode` file
5. **Optionally click "Show 3D Preview"** to inspect the model before printing

### Advanced Settings

Toggle "Show advanced settings" in the sidebar to access:

- Print parameters (nozzle temp, bed temp, speed, fan)
- Extrusion geometry (width, layer height, band height)
- Design tuning (wiggle amplitude/frequency, text size)
- Quality presets (50k / 100k / 150k points per spiral)
- Ease-in/out settings for clean top and bottom edges

## Printing Tips

- **Measuring your wrist:** Wrap a tape measure snugly around the wrist and note the circumference in mm. The band stretches slightly, so a snug fit is fine. Currently would recommend to deduct 10mm.
- **Material:** Use TPU (flexible filament). 95A is just fine. Softer ones might be smoother but are more expensive and more difficult to print.
- **Bed adhesion:** TPU sticks well to PEI and glass beds.
- **First layer:** Print slowly (~50 % speed) for good adhesion. The default ease-in settings handle this.
- **Temperatures:** Defaults are nozzle 220 °C / bed 60 °C. Lower to ~210 °C for softer TPU.
- **Speed:** TPU prints best at moderate speeds. The default 1100 mm/min (~18 mm/s) is a safe starting point. Bowden extruders may need slower.
- **Removing from bed:** Let the print cool fully before removing — TPU peels off easily once cool.
- **Multi-band prints:** Check that all bands fit on your printer's bed. The app warns you if the grid footprint exceeds the build area. But you can indeed push the limits with the spacing (because we are dealing with TPU here). So although the print head might collide with an already printed band it pushed the old one aside with ease. That way i could easily fit 3x3 bands on my 250x250 buildplate.

## Project Structure

```
uwr_wristband/
├── app.py                      # Streamlit frontend
├── uwr_wristband/
│   ├── generator.py            # Core spiral generation + G-code output
│   ├── printers.py             # Printer profile loading + build volumes
│   ├── defaults.py             # Default parameters + presets
│   └── visualization.py        # 3D preview (plotly)
├── requirements.txt
├── pyproject.toml
└── LICENSE                     # MIT
```

## How It Works

The wristband is generated as a continuous spiral path with a sinusoidal radial wiggle (meander pattern). Text is converted to polygons using Matplotlib's font rendering, then projected into (Y, Z) space around the cylinder. Points inside text regions get an amplified wiggle, creating a raised emboss effect.

The spiral generation uses vectorized [Shapely 2.0](https://shapely.readthedocs.io/) `contains_xy()` for fast point-in-polygon testing (~10x faster than per-point checks). G-code is produced by [fullcontrol](https://github.com/FullControlXYZ/fullcontrol), which handles printer-specific start/end sequences, extrusion math, and travel moves.

## A Note on How This Was Built

The Streamlit app, project structure, and UI wiring were vibecoded with the help of Claude Code. However, the core wristband generation logic — the spiral-meander math, text polygon projection, ease-in/out curves, grid assembly, and the fullcontrol integration — was carefully designed, tested, and iterated on by hand over multiple print cycles. The geometry had to be right to produce bands that actually print well, flex correctly, and look good on a wrist. AI helped scaffold the webapp; the engineering behind the G-code is human. I have printed at least >100 bands during the making of this code.

## Disclaimer

Running generated G-code on your 3D printer is entirely at your own risk. Always review the G-code and verify printer settings before printing. Incorrect settings can damage your printer or cause a fire hazard. Make sure you understand what you are doing.

## License

MIT License. See [LICENSE](LICENSE) for details.
