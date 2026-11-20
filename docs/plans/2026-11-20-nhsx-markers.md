# Hindenburg markers (owner issue 38)

The NHSX importer kept the source XML but did not turn session markers into
Kuulas markers. It now imports ordinary points in timeline frames using the
shared NHSX time parser. IDs 1 and 2 seed the transport In/Out range instead
of becoming duplicate numbered sidebar markers. The launcher and command-line
import seed the remembered view; importing into an open editor also returns
the marks in the command response.

Markers belong to the import's single undo step. Transport marks remain view
state, consistent with ordinary In/Out actions. Invalid optional marker times
are not placed at zero and do not discard valid audio. Source XML is retained.
An inverted transport range is not used. A marker-only import reports success
rather than saying that nothing was imported.

Verification: failing-first session/API and UI-result regressions; existing
NHSX, launcher, marker, view-memory and resume tests. Native Mac verification
and real owner sessions remain separate checks.
