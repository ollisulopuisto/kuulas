// The toolbar's buttons as data (WP86): the layout turned into { id, label, tip, enabled, icon }.
// Pure: the registry, the state, the translator and the key lookup are passed in. The order is
// the layout's and nothing else's; a command that cannot run is only `enabled: false`.

/**
 * The icon of each default command (icons.js), or null where there is none yet: a null is drawn
 * as text so the button is never empty. Icons for transcribe, Auto-Silence, resync and automix
 * are still to be chosen (docs/design/TOOLBAR.md, open questions).
 */
export const TOOLBAR_ICONS = Object.freeze({
  "edit.undo": "undo",
  "edit.redo": "redo",
  "app.import": "import",
  "app.transcribe": null,
  "app.auto_silence": null,
  "edit.split": "cut",
  "clip.mute": "mute",
  "sync.resync_range": null,
  "export.automix": null,
  "app.export": "export",
});

/** `layout`: command ids; `registry`: { has, can }; `t`: translate; `keyOf(id)`: the key text or "". */
export function toolbarItems({ layout, registry, state, t, keyOf }) {
  return layout.map((id) => {
    const label = t(`cmd.${id}`);
    const key = keyOf(id);
    return {
      id,
      label,
      tip: key ? `${label} (${key})` : label,
      enabled: registry.has(id) && registry.can(id, state),
      icon: TOOLBAR_ICONS[id] ?? null,
    };
  });
}
