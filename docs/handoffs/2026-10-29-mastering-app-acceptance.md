# Shared mastering: whole-app boundary and remaining gates

User scope: whole-programme -16 LUFS with parity, global decisions, cancellation,
partial cleanup and10/30/90resource acceptance; sync Kuulas and Podcast.

Prior lead Oct28 passed sharedAPI Linux/Mac/nativeMLX/resource/CLI gates.
Do not repeat those or infer that they enable Kuulas. Production remains
STREAM_MASTERING_ENABLED=False, legacy RAM guard unchanged.

On Kuulas80d87630 with sibling Podcastc5ea198 editable speechmix, new public
Session.export→realWAV short parity matches old output within1e-7 and identical
global report; target reached.24candidate/Session focused tests pass.

New explicit scripts/master_export_acceptance.py measures real Session import,
mixer, disk-backed candidate master, final floatWAV and incremental measurement.
It opts into candidate and bypasses ONLY the legacy duration-scaled admission
in its isolated test process, clearly reported in JSON. It does not change
production admission or defaults. Without that test bypass10/30both refuse
beforeDSP because old guard estimates whole-programme memory (~4min here).

10min: RSSpeak286011392B, incremental151453696B,11.67s export.
30min: RSSpeak348909568B, incremental212840448B,33.27s export.
Both exactly expected frames, measured-16LUFS, right/leftRMS.6, zero partials.
Synthetic repeated tone is resource/boundary proof, not real-episode audition.
90min preflight refused18729508864Brequired vs12027518976Bfree, no long
allocation. Do not call90min whole-app acceptance passed from sharedAPI tests.

Packaging gap: dmg.yml pins Podcast7793c0c1b276e90e466cea6d0b09e20fca08c968,
which has no master_stream; developer source has it. Boundedtruepeak fix
44a688c30ddbbc00b3ab1b5c8bfd07ca5ca699f4 not in that pinned revision.
Updating bundled Podcast also changes other apps/tools, so audit pair and
request scoped workflow-pin review. No workflow patch/default activation yet.
Shared package version2026.10.9.1 alone is insufficient commit provenance.

Still open:90whole-app resource run with enough disk; native whole-app parity
and real-episode audition; candidate RAM admission contract measured across
render concurrency; exact immutable package pair and bundled smoke, then an
explicit default/paired-release decision. Legacy remains safe and working.

Immutable wheel check: built clean detached Podcast
44a688c30ddbbc00b3ab1b5c8bfd07ca5ca699f4 speechmix2026.10.9.1wheel,
SHA256c3a69be3aa7a41ca1c8f9766bd6001192b09a2076451437b2e174fdbabe38bb9.
Verified streaming.py and programme.master_stream in wheel; imported this
unpacked wheel ahead of editable source and all24Session/adaptertests pass.
This clears the Linux wheel/API boundary, not native app bundling. Compared to
oldpin, nhsx/silencelearn source unchanged; automixer changes are version/docs
only in that path. Other bundled tool changes still need full pair review.
No workflowpin change made. Candidatepin is a proposal, not authorizedactivation.
