"""UWR Wristband Generator."""

# App version — bump when UI, settings, or non-generation code changes.
APP_VERSION = "1.0.0"

# Band version — bump when generation logic changes (spiral math, text
# projection, grid assembly, G-code output).  This is embedded in every
# generated G-code file so prints can be traced back to the exact generator
# revision.
BAND_VERSION = "1.0.0"
