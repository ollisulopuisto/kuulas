# Cart playback during a take

A recording-time clipboard preview uses the cart track chosen at Record setup.
The server measures the entry on that track, matches its level and logs the
paste with that same gain added to each source clip's existing gain. The
normal preview attenuation preference does not disable cart matching. Ordinary
track mix controls still apply when listening to the resulting timeline.

Voice estimation uses a three-second rolling power average of recorder channel
peaks above -60 dBFS, minus the existing preview estimate of 14 dB from peak to
LUFS. It is an approximation, not a loudness meter. Until voices are available
(or when the samples expire), the project's preview reference is used. Manual
trim is a per-user browser preference, default 0 dB, bounded to +/-12 dB. The
entry's measured true peak caps the final gain at -1 dBTP. Unknown peaks cannot
be boosted. The preview has no extra soft limiter in cart mode: playback and
logged gain use the same linear adjustment.

Only clip IDs issued by the active RecordSession can be ended through
`POST /api/record/cart/end {clip_ids}`. The UI reports preview ends (chip Stop,
repeated cart key, transport Stop, or natural end). Rapid cart key actions are
serialized. A replacement also finishes the previous play on the server before
its new paste. Late end notifications for older plays are harmless.

The start and stop use the recorder's latest position_frames, translated by the
take plan's timeline offset and pre-roll. On take stop, final sidecar segment
ends supply the position (including gaps). Each shortened play is one history
commit named cart_end; it trims only its issued IDs. Ordinary trim commands
remain paused during recording. A stop at or before a clip's start leaves one
frame. Nothing extends a clip, ripples another clip, or modifies a media file.

No project format changes: lengths and gain_db are existing clip fields. A
microphone take, actual output sound, and device coexistence need a live check.
