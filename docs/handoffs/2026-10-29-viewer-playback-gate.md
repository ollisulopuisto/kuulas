# Playback support gate after native golden success

Native run40864194887 onb0cc345b passed9Swift tests, including stereo,
mono-downmix, crossfade/bus/solo/mute golden windows and bounds, plus app and
embedded QuickLook build/bundle checks. Actual logs retrieved and inspected.

Remove unconditional unverified-audio denial only for conformance-covered
schema. Unknown project/track/bus/clip fields and malformed numeric/curve data
refuse rather than silently simplifying audio. Controller and player init
both enforce the gate. External linked files and unsupported media rates or
channel counts still refuse in AudioFiles. No broad sandbox exception.

11portableViewer tests/Ruff/diff pass. New gate tests must pass natively
before artifact is usable. Native transport lifecycle still needs real Mac
seek/pause/edit/close/end audition and visual/Finder acceptance. Golden sample
equivalence does not prove UI/controller lifecycle or live device playback.
First no-audio preview already delivered; this is a separate candidate.
