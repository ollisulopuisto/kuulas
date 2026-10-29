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
