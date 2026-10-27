# Packaged Orukeet HTTPS trust implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

The packaged Python has no reliable OpenSSL root certificate path. The model
installer uses urllib's implicit default trust store, while source-checkout tests
borrow the developer Python's certificates. Supply certifi as a direct production
dependency and explicitly add its CA bundle to a verified download context.

1. Reproduce installation with nonexistent default CA paths; require a populated
   trust store, certificate verification and hostname checks on every request.
2. Verify a certificate error remains a hard failure and preserves the old model.
3. Add the context to the downloader and certifi to the app's dependencies.
4. Add an offline certificate-store selftest. During DMG builds, opt into a tiny
   real HTTPS request to the pinned weight file, including its CDN redirect; run
   that from both the built app and the app mounted from the DMG. Normal offline
   selftests should not need the network. Never disable TLS verification.
5. Validate focused tests and a real HTTPS probe with default CA paths missing;
   run required full checks, document, release v26.10.27.3 and verify both packaged
   network probes and the release asset checksum.

Owner steering adds toolbar discoverability to this release: a fixed dashed plus
slot opens a searchable command picker; menu rows no longer expose toolbar
context actions. Drag-away removal previews intent and supports Escape and Undo,
while in-rail reordering remains unchanged. Pure tests cover eligible commands,
search, duplicate exclusion and the clear removal margin. Chrome verified add
without execution, persistence, cancellation, removal/Undo, reordering and menu
behavior without page errors.

Focused TLS checks pass (60 tests). With both default CA paths deliberately
missing, the default context had zero roots; the downloader context had 118 roots
and verified a real request to the pinned model's weight/CDN endpoint. No TLS
verification flags were weakened.

Release validation before integration: 5,197 Python tests passed (one upstream
Starlette deprecation warning), 3,599 UI tests passed, Ruff and Biome clean.
The shared model/CDN probe also passed with all default CA paths missing.
The owner's new recording-view reports are tracked as BUGS #136–138 for a
separate follow-up; no recording engine/UI changes ship in this hotfix.

The owner cancelled the standalone v26.10.27.3 build. These changes are included in the combined v26.10.27.4 release.
