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

**Slicer preview:** Orca Slicer (and other Orca-based slicers) may display the G-code
flat in one plane — the Z height looks wrong in the preview. This is a display issue
only; the actual print uses the correct Z values and prints fine.

**Removing from bed:** Let the print cool fully before removing — TPU peels off
easily once cool.

**Multi-band prints:** Check that all bands fit on your printer's bed. The app warns
you if the grid footprint exceeds the build area. But you can indeed push the limits
with the spacing (because we are dealing with TPU here). So although the print head
might collide with an already printed band it pushes the old one aside with ease.
That way you can easily fit 3x3 bands on a 250x250 build plate.
