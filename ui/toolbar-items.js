// The toolbar's buttons as data (WP86): the layout turned into { id, label, tip, enabled, icon }.
// Pure: the registry, the state, the translator and the key lookup are passed in. The order is
// the layout's and nothing else's; a command that cannot run is only `enabled: false`.

/**
 * The icon of each default command (icons.js), or null: a null is drawn as text so a button is
 * never empty. Every default button has an icon of its own (a test checks it).
 */
export const TOOLBAR_ICONS = Object.freeze({
  "edit.undo": "undo",
  "edit.redo": "redo",
  "app.import": "import",
  "app.transcribe": "transcribe",
  "app.auto_silence": "silence",
  "edit.split": "cut",
  "clip.mute": "mute",
  "sync.resync_range": "resync",
  "export.automix": "automix",
  "app.export": "export",
});

/**
 * The short label of each default button (message keys): the rail is narrow, and the full command
 * names ("Transcribe the track on this computer") do not fit it. The tip keeps the full name.
 * A command the user pins that is not listed shows its full name.
 */
export const SHORT_LABELS = Object.freeze(
  Object.fromEntries(Object.keys(TOOLBAR_ICONS).map((id) => [id, `ui.rail.short.${id}`])),
);

const BADGE_MAX = 99;

/** How many silent stretches Auto-Silence has found, over every clip, as button text; null for none. */
function silenceBadge(state) {
  let count = 0;
  for (const track of state?.project?.tracks ?? [])
    for (const clip of track.clips ?? []) count += clip.auto_silence?.length ?? 0;
  if (count === 0) return null;
  return count > BADGE_MAX ? `${BADGE_MAX}+` : String(count);
}

const BADGES = Object.freeze({ "app.auto_silence": silenceBadge });

/** `layout`: command ids; `registry`: { has, can }; `t`: translate; `keyOf(id)`: the key text or "". */
export function toolbarItems({ layout, registry, state, t, keyOf }) {
  return layout.map((id) => {
    const full = t(`cmd.${id}`);
    const key = keyOf(id);
    return {
      id,
      label: id in SHORT_LABELS ? t(SHORT_LABELS[id]) : full,
      tip: key ? `${full} (${key})` : full,
      enabled: registry.has(id) && registry.can(id, state),
      icon: TOOLBAR_ICONS[id] ?? null,
      badge: BADGES[id]?.(state) ?? null,
    };
  });
}
