# Live output RMS alongside LUFS

Follow-up to merged PR85, which restored missing LUFS wire data. Forward the
already-measured rms_l/rms_r as well, and draw independent left/right RMS bars
beside the three-second LUFS bar. dBFS average level, not a calibrated VU meter;
no new audio DSP. Peaks remain only the separate clip latch. Labels/tooltips
in English and Finnish; stopped/missing RMS returns both bars to floor.

Red tests showed missing RMS fields; gain/pan/mute parametrized regression now
compares the serialized RMS to the actual engine callback output for each
channel.143 focused server/engine-meter/shared-LUFS tests pass. Fixture pixels
in real Chromium Finnish/dark show independent L/R and LUFS levels changing,
then reset on floor. Native playback/listening/full editor acceptance remains
open. No recording-meter ownership changes. Whole repo Ruff and UI Biome clean.

Full statusbar markup fixture checked at1512px (3024px Retina screenshot
candidate),1200,1000,800 with range, scope, series, transcription notice,
version, help and View controls populated. At800px the first check exposed
clipped version/menu controls. Added compact meter widths/gaps and passive
scope suppression with ellipsized range under900px; checked updated pixels
and geometry, all controls inside viewport at800px.1512px unchanged. This
uses actual footer markup/CSS and fixture text, not the whole running editor.
3631 Node tests and full UI Biome pass after layout fix.

Second visual review caught active transcription notice shrinking away. Fixed
shrink priority: notice is nonshrinking; passive keyboard hints yield under1250,
range under1100 and zoom under900. Rechecked800/1000 actual pixels with full
“Litteroidaan 32 %” retained, menus/version/dual meter readable. Meter font
size unchanged.1512/1200 also fit. Passive data remain elsewhere in UI.
