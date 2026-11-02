# Palette's Journal - Critical UX/Accessibility Learnings

## 2026-11-02 - Command Catalog as the Single Source for ARIA Labels
**Learning:** Command-driven interactive buttons (with `data-cmd`) often contain icon-only visual markup or terse text (like Loop or Fit buttons). While keyboard shortcuts and descriptions are kept centrally in `DEFAULT_KEYMAP` and locale catalogs (`labelKey`), buttons lacking explicit `aria-label` or `aria-labelledby` attributes risk silence or non-descriptive screen reader announcements. Dynamically deriving `aria-label` from `entry.labelKey` via `t()` and tracking auto-assigned labels with `data-cmd-aria-label="auto"` ensures consistent accessible names across locales without overwriting custom explicit labels.
**Action:** When wiring keyboard shortcuts and accessible labels on `[data-cmd]` elements, always derive fallback `aria-label` attributes directly from the central command registry's `labelKey`.
