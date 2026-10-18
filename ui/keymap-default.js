// The default keymap, as data. One entry per command id:
//   keys     the combos per platform (a string, a list of aliases, or null for no key).
//            "Mod" is Cmd on a Mac and Ctrl elsewhere; see keys.js for the grammar.
//   context  where it works: "global" (any panel, not while typing), "timeline",
//            "transcript", "side" (inspector and history), or "text-field" (also
//            while typing: Esc, F6, the palette).
//   labelKey the command's name in the catalogs (also what the palette searches).
//   repeat   a held key fires again.
// Users override single commands in localStorage (keymap-config.js); this file is
// not edited at run time. The collision test (tests/keymap-default.test.js) must
// pass for it on both platforms.
//
// Zoom keys (owner, 2026-10-18): Z toggles close and wide, 0 shows the whole edit, F fits the
// selection or in-out; no view command lives on a modified Z (Cmd+Z and Cmd+Shift+Z are undo and redo).
// Owner decisions (18.10.2026) kept here: Backspace is Delete (soft cut, gap kept),
// X is Cut (ripple, to the clipboard), Mod+C copies; Spot is Mod+J, find is Mod+F,
// fade is G, import is Mod+I (Mod+T in the desktop wrapper), K keeps a candidate (in the Candidates tab),
// [ ] are physical keys (Finnish Mac: Option+8/9, so Alt+Down/Up also step candidates and
// Alt+Mod+Shift+Left/Right the views; Alt+Shift+Arrow is pan), F2 renames. Alt+X is lift-cut
// (copy, then soft delete, gap kept), Alt+Mod+X closes the gap on all tracks (ripple, no
// clipboard). Parked and so not bound: Clean up cuts, Compare. The clipboard (WP46): X cuts to it,
// Mod+C copies only, Backspace never touches it; Mod+V pastes (insert), Alt+Mod+V
// overwrites, Shift+Mod+V inserts on the current track.
// J/K/L (WP26): J, K and L are the shuttle keys in every panel. In the Candidates tab Enter
// keeps the candidate and Backspace/Delete deletes it (owner, 2026-10-18).

import { EXPORT_FORMAT_IDS } from "./export-commands.js";

export const CONTEXTS = [
  "global",
  "not-candidates",
  "not-transcript",
  "timeline",
  "transcript",
  "side",
  "candidates",
  "text-field",
];

export const DEFAULT_KEYMAP = [
  {
    id: "transport.play",
    keys: { mac: "Space", other: "Space" },
    context: "global",
    labelKey: "cmd.transport.play",
  },
  {
    id: "transport.play_before",
    keys: { mac: "P", other: "P" },
    context: "global",
    labelKey: "cmd.transport.play_before",
  },
  {
    id: "transport.play_selection",
    keys: { mac: "Shift+Space", other: "Shift+Space" },
    context: "timeline",
    labelKey: "cmd.transport.play_selection",
  },
  {
    id: "view.drag_mode",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.view.drag_mode",
  },
  {
    id: "transport.rehearse",
    keys: { mac: "Shift+Mod+Space", other: "Shift+Mod+Space" },
    context: "timeline",
    labelKey: "cmd.transport.rehearse",
  },

  {
    id: "transport.speed",
    keys: { mac: ".", other: "." },
    context: "timeline",
    labelKey: "cmd.transport.speed",
  },
  {
    // Fast listening's speed is stepless, 1.0x to 2.0x in 0.05x steps (owner, 2026-10-18).
    // Shift+. and Shift+, cannot be told from . and , (shift is part of the character), so
    // the nudges are , (slower) and / (faster); Alt+0 puts it back to 1.0x.
    id: "transport.speed_down",
    keys: { mac: ",", other: "," },
    context: "global",
    labelKey: "cmd.transport.speed_down",
    repeat: true,
  },
  {
    id: "transport.speed_up",
    keys: { mac: "/", other: "/" },
    context: "global",
    labelKey: "cmd.transport.speed_up",
    repeat: true,
  },
  {
    id: "transport.speed_reset",
    keys: { mac: "Alt+0", other: "Alt+0" },
    context: "global",
    labelKey: "cmd.transport.speed_reset",
  },
  {
    // Mod+L is Automix; Alt or Shift variants of a taken key would show up as menu alternates.
    id: "transport.loop",
    keys: { mac: "Mod+U", other: "Mod+U" },
    context: "global",
    labelKey: "cmd.transport.loop",
  },
  {
    id: "transport.shuttle_back",
    keys: { mac: "J", other: "J" },
    context: "global",
    labelKey: "cmd.transport.shuttle_back",
  },
  {
    id: "transport.shuttle_forward",
    keys: { mac: "L", other: "L" },
    context: "global",
    labelKey: "cmd.transport.shuttle_forward",
  },
  {
    id: "transport.shuttle_stop",
    keys: { mac: "K", other: "K" },
    context: "global",
    labelKey: "cmd.transport.shuttle_stop",
  },
  {
    id: "nav.home",
    keys: { mac: "Escape", other: "Escape" },
    context: "text-field",
    labelKey: "cmd.nav.home",
  },
  {
    id: "nav.start",
    keys: { mac: "Home", other: "Home" },
    context: "timeline",
    labelKey: "cmd.nav.start",
  },
  {
    id: "nav.end",
    keys: { mac: "End", other: "End" },
    context: "timeline",
    labelKey: "cmd.nav.end",
  },
  {
    // The automatic "left off" marker (left-off.js). No chord: every sensible one is taken,
    // and it is a command for the Go menu and the palette that is used once per session.
    id: "nav.to_resume",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.nav.to_resume",
  },
  {
    id: "nav.back",
    keys: { mac: "ArrowLeft", other: "ArrowLeft" },
    context: "timeline",
    labelKey: "cmd.nav.back",
    repeat: true,
  },
  {
    id: "nav.forward",
    keys: { mac: "ArrowRight", other: "ArrowRight" },
    context: "timeline",
    labelKey: "cmd.nav.forward",
    repeat: true,
  },
  {
    id: "nav.back_far",
    keys: { mac: "Shift+ArrowLeft", other: "Shift+ArrowLeft" },
    context: "timeline",
    labelKey: "cmd.nav.back_far",
    repeat: true,
  },
  {
    id: "nav.forward_far",
    keys: { mac: "Shift+ArrowRight", other: "Shift+ArrowRight" },
    context: "timeline",
    labelKey: "cmd.nav.forward_far",
    repeat: true,
  },
  {
    id: "nav.back_fine",
    keys: { mac: "Alt+ArrowLeft", other: "Alt+ArrowLeft" },
    context: "timeline",
    labelKey: "cmd.nav.back_fine",
    repeat: true,
  },
  {
    id: "nav.forward_fine",
    keys: { mac: "Alt+ArrowRight", other: "Alt+ArrowRight" },
    context: "timeline",
    labelKey: "cmd.nav.forward_fine",
    repeat: true,
  },
  // Tab to the next word or transient (WP19i). Tab keeps its focus move in the side
  // panels and in text fields: it is bound in the timeline and the transcript only (one
  // entry each, a keymap entry has one context). Alt+Tab (Shift+T off the Mac) cycles the level.
  {
    id: "nav.prev_stop",
    keys: { mac: "Shift+Tab", other: "Shift+Tab" },
    context: "timeline",
    labelKey: "cmd.nav.prev_stop",
  },
  {
    id: "nav.next_stop",
    keys: { mac: "Tab", other: "Tab" },
    context: "timeline",
    labelKey: "cmd.nav.next_stop",
  },
  {
    id: "transcript.prev_stop",
    keys: { mac: "Shift+Tab", other: "Shift+Tab" },
    context: "transcript",
    labelKey: "cmd.transcript.prev_stop",
  },
  {
    id: "transcript.next_stop",
    keys: { mac: "Tab", other: "Tab" },
    context: "transcript",
    labelKey: "cmd.transcript.next_stop",
  },
  {
    id: "nav.tab_target_cycle",
    keys: { mac: "Alt+Tab", other: "Shift+T" },
    context: "global",
    labelKey: "cmd.nav.tab_target_cycle",
  },
  {
    id: "track.prev",
    keys: { mac: "ArrowUp", other: "ArrowUp" },
    context: "timeline",
    labelKey: "cmd.track.prev",
    repeat: true,
  },
  {
    id: "track.next",
    keys: { mac: "ArrowDown", other: "ArrowDown" },
    context: "timeline",
    labelKey: "cmd.track.next",
    repeat: true,
  },
  {
    id: "history.restore",
    keys: { mac: "Enter", other: "Enter" },
    context: "side",
    labelKey: "cmd.history.restore",
  },
  {
    id: "history.open",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.history.open",
  },
  {
    id: "panel.next",
    keys: { mac: "F6", other: "F6" },
    context: "text-field",
    labelKey: "cmd.panel.next",
  },
  {
    id: "panel.previous",
    keys: { mac: "Shift+F6", other: "Shift+F6" },
    context: "text-field",
    labelKey: "cmd.panel.previous",
  },
  {
    id: "mark.in",
    keys: { mac: ["I", "Mod+1"], other: ["I", "Mod+1"] },
    context: "timeline",
    labelKey: "cmd.mark.in",
  },
  {
    id: "mark.out",
    keys: { mac: ["O", "Mod+2"], other: ["O", "Mod+2"] },
    context: "timeline",
    labelKey: "cmd.mark.out",
  },
  {
    id: "nav.to_in",
    keys: { mac: "1", other: "1" },
    context: "timeline",
    labelKey: "cmd.nav.to_in",
  },
  {
    id: "nav.to_out",
    keys: { mac: "2", other: "2" },
    context: "timeline",
    labelKey: "cmd.nav.to_out",
  },
  {
    id: "mark.clear_in",
    keys: { mac: "Shift+I", other: "Shift+I" },
    context: "timeline",
    labelKey: "cmd.mark.clear_in",
  },
  {
    id: "mark.clear_out",
    keys: { mac: "Shift+O", other: "Shift+O" },
    context: "timeline",
    labelKey: "cmd.mark.clear_out",
  },
  {
    id: "mark.clear",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.mark.clear",
  },
  {
    id: "view.toggle",
    keys: { mac: "Z", other: "Z" },
    context: "global",
    labelKey: "cmd.view.toggle",
  },
  {
    id: "view.fit",
    keys: { mac: "0", other: "0" },
    context: "global",
    labelKey: "cmd.view.fit",
  },
  {
    id: "view.fit_selection",
    keys: { mac: "F", other: "F" },
    context: "global",
    labelKey: "cmd.view.fit_selection",
  },
  {
    id: "view.back",
    keys: {
      mac: ["Alt+[", "Alt+Mod+Shift+ArrowLeft"],
      other: ["Alt+[", "Alt+Mod+Shift+ArrowLeft"],
    },
    context: "global",
    labelKey: "cmd.view.back",
  },
  {
    id: "view.forward",
    keys: {
      mac: ["Alt+]", "Alt+Mod+Shift+ArrowRight"],
      other: ["Alt+]", "Alt+Mod+Shift+ArrowRight"],
    },
    context: "global",
    labelKey: "cmd.view.forward",
  },
  {
    id: "view.zoom_in",
    keys: { mac: ["=", "+"], other: ["=", "+"] },
    context: "global",
    labelKey: "cmd.view.zoom_in",
    repeat: true,
  },
  {
    id: "view.zoom_out",
    keys: { mac: "-", other: "-" },
    context: "global",
    labelKey: "cmd.view.zoom_out",
    repeat: true,
  },
  {
    id: "edit.undo",
    keys: { mac: "Mod+Z", other: "Mod+Z" },
    context: "global",
    labelKey: "cmd.edit.undo",
  },
  {
    id: "edit.redo",
    keys: { mac: "Shift+Mod+Z", other: ["Shift+Mod+Z", "Mod+Y"] },
    context: "global",
    labelKey: "cmd.edit.redo",
  },
  {
    id: "edit.copy",
    keys: { mac: "Mod+C", other: "Mod+C" },
    context: "global",
    labelKey: "cmd.edit.copy",
  },
  {
    id: "edit.paste",
    keys: { mac: "Mod+V", other: "Mod+V" },
    context: "global",
    labelKey: "cmd.edit.paste",
  },
  {
    id: "edit.paste_overwrite",
    keys: { mac: "Alt+Mod+V", other: "Alt+Mod+V" },
    context: "global",
    labelKey: "cmd.edit.paste_overwrite",
  },
  {
    id: "edit.paste_track",
    keys: { mac: "Shift+Mod+V", other: "Shift+Mod+V" },
    context: "global",
    labelKey: "cmd.edit.paste_track",
  },
  // Fixed forms of the other two paste choices: unbound, in the Edit menu and the palette.
  {
    id: "edit.paste_same",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.edit.paste_same",
  },
  {
    id: "edit.paste_overwrite_track",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.edit.paste_overwrite_track",
  },
  {
    id: "edit.preview_clipboard",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.edit.preview_clipboard",
  },
  {
    id: "edit.split",
    keys: { mac: ["B", "Mod+B"], other: ["B", "Mod+B"] },
    context: "timeline",
    labelKey: "cmd.edit.split",
  },
  {
    id: "edit.group",
    keys: { mac: "Alt+Mod+G", other: "Alt+Mod+G" },
    context: "timeline",
    labelKey: "cmd.edit.group",
  },
  {
    id: "edit.ungroup",
    keys: { mac: "Shift+Alt+Mod+G", other: "Shift+Alt+Mod+G" },
    context: "timeline",
    labelKey: "cmd.edit.ungroup",
  },
  {
    id: "edit.merge",
    keys: { mac: "Alt+Mod+J", other: "Alt+Mod+J" },
    context: "timeline",
    labelKey: "cmd.edit.merge",
  },
  {
    id: "edit.split_all",
    keys: { mac: "Shift+B", other: "Shift+B" },
    context: "timeline",
    labelKey: "cmd.edit.split_all",
  },
  {
    id: "edit.remove_clips",
    keys: { mac: "Mod+Backspace", other: "Mod+Backspace" },
    context: "not-transcript",
    labelKey: "cmd.edit.remove_clips",
  },
  {
    id: "edit.remove",
    keys: { mac: "X", other: "X" },
    context: "not-transcript",
    labelKey: "cmd.edit.remove",
  },
  {
    id: "edit.remove_track",
    keys: { mac: "Shift+X", other: "Shift+X" },
    context: "not-transcript",
    labelKey: "cmd.edit.remove_track",
  },
  {
    id: "edit.cut",
    keys: { mac: "Mod+X", other: "Mod+X" },
    context: "not-transcript",
    labelKey: "cmd.edit.cut",
  },
  {
    id: "edit.cut_track",
    keys: { mac: "Shift+Mod+X", other: "Shift+Mod+X" },
    context: "not-transcript",
    labelKey: "cmd.edit.cut_track",
  },
  {
    id: "edit.lift_cut",
    keys: { mac: "Alt+X", other: "Alt+X" },
    context: "not-transcript",
    labelKey: "cmd.edit.lift_cut",
  },
  {
    id: "edit.close_gap_all",
    keys: { mac: "Alt+Mod+X", other: "Alt+Mod+X" },
    context: "not-transcript",
    labelKey: "cmd.edit.close_gap_all",
  },
  {
    id: "edit.delete",
    keys: { mac: ["Backspace", "Delete"], other: ["Backspace", "Delete"] },
    context: "timeline",
    labelKey: "cmd.edit.delete",
  },
  {
    id: "edit.trim_start",
    keys: { mac: "Q", other: "Q" },
    context: "timeline",
    labelKey: "cmd.edit.trim_start",
  },
  {
    id: "edit.trim_end",
    keys: { mac: "W", other: "W" },
    context: "timeline",
    labelKey: "cmd.edit.trim_end",
  },
  {
    id: "edit.nudge_left",
    keys: { mac: "Mod+ArrowLeft", other: "Mod+ArrowLeft" },
    context: "timeline",
    labelKey: "cmd.edit.nudge_left",
    repeat: true,
  },
  {
    id: "edit.nudge_right",
    keys: { mac: "Mod+ArrowRight", other: "Mod+ArrowRight" },
    context: "timeline",
    labelKey: "cmd.edit.nudge_right",
    repeat: true,
  },
  {
    id: "edit.move_up",
    keys: { mac: "Mod+ArrowUp", other: "Mod+ArrowUp" },
    context: "timeline",
    labelKey: "cmd.edit.move_up",
  },
  {
    id: "edit.move_down",
    keys: { mac: "Mod+ArrowDown", other: "Mod+ArrowDown" },
    context: "timeline",
    labelKey: "cmd.edit.move_down",
  },
  {
    id: "edit.select_all_track",
    keys: { mac: "Mod+A", other: "Mod+A" },
    context: "global",
    labelKey: "cmd.edit.select_all_track",
  },
  {
    id: "edit.select_all",
    keys: { mac: "Alt+Mod+A", other: "Alt+Mod+A" },
    context: "global",
    labelKey: "cmd.edit.select_all",
  },
  {
    id: "select.to_end",
    keys: { mac: "Shift+End", other: "Shift+End" },
    context: "timeline",
    labelKey: "cmd.select.to_end",
  },
  {
    id: "select.to_start",
    keys: { mac: "Shift+Home", other: "Shift+Home" },
    context: "timeline",
    labelKey: "cmd.select.to_start",
  },
  {
    id: "select.to_end_all",
    keys: { mac: "Shift+Alt+End", other: "Shift+Alt+End" },
    context: "timeline",
    labelKey: "cmd.select.to_end_all",
  },
  {
    id: "select.to_start_all",
    keys: { mac: "Shift+Alt+Home", other: "Shift+Alt+Home" },
    context: "timeline",
    labelKey: "cmd.select.to_start_all",
  },
  // WP54. Unbound: no free key worth taking; they are in the Edit > Select menu and the palette.
  {
    id: "select.range_all_tracks",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.select.range_all_tracks",
  },
  {
    id: "select.clips_in_range",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.select.clips_in_range",
  },
  {
    id: "select.range_from_clips",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.select.range_from_clips",
  },
  {
    id: "select.forward",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.select.forward",
  },
  {
    id: "select.forward_from_clips",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.select.forward_from_clips",
  },
  {
    id: "select.forward_all_tracks_from_clips",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.select.forward_all_tracks_from_clips",
  },
  {
    id: "select.invert",
    keys: { mac: "Shift+Mod+A", other: "Shift+Mod+A" },
    context: "timeline",
    labelKey: "cmd.select.invert",
  },
  {
    id: "select.none",
    // Not Escape: nav.home has it in every context.
    keys: { mac: "Mod+D", other: "Mod+D" },
    context: "timeline",
    labelKey: "cmd.select.none",
  },
  {
    id: "clip.gain_up",
    keys: { mac: "Shift+Mod+ArrowUp", other: "Shift+Mod+ArrowUp" },
    context: "timeline",
    labelKey: "cmd.clip.gain_up",
    repeat: true,
  },
  {
    id: "clip.gain_down",
    keys: { mac: "Shift+Mod+ArrowDown", other: "Shift+Mod+ArrowDown" },
    context: "timeline",
    labelKey: "cmd.clip.gain_down",
    repeat: true,
  },
  {
    id: "clip.pan_left",
    keys: { mac: "Shift+Alt+ArrowLeft", other: "Shift+Alt+ArrowLeft" },
    context: "timeline",
    labelKey: "cmd.clip.pan_left",
    repeat: true,
  },
  {
    id: "clip.pan_right",
    keys: { mac: "Shift+Alt+ArrowRight", other: "Shift+Alt+ArrowRight" },
    context: "timeline",
    labelKey: "cmd.clip.pan_right",
    repeat: true,
  },
  {
    id: "clip.mute",
    keys: { mac: ["M", "Alt+Mod+M"], other: ["M", "Alt+Mod+M"] },
    context: "timeline",
    labelKey: "cmd.clip.mute",
  },
  {
    id: "clip.fade",
    keys: { mac: "G", other: "G" },
    context: "timeline",
    labelKey: "cmd.clip.fade",
  },
  {
    id: "clip.match_loudness",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.clip.match_loudness",
  },
  {
    id: "track.mute",
    keys: { mac: "Shift+M", other: "Shift+M" },
    context: "timeline",
    labelKey: "cmd.track.mute",
  },
  {
    id: "track.solo",
    keys: { mac: "Shift+S", other: "Shift+S" },
    context: "timeline",
    labelKey: "cmd.track.solo",
  },
  {
    id: "track.solo_add",
    keys: { mac: "Shift+Alt+S", other: "Shift+Alt+S" },
    context: "timeline",
    labelKey: "cmd.track.solo_add",
  },
  {
    id: "track.add",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.track.add",
  },
  {
    id: "track.add_music",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.track.add_music",
  },
  {
    id: "track.delete_empty",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.track.delete_empty",
  },
  {
    id: "track.cycle_kind",
    keys: { mac: "Alt+Mod+K", other: "Alt+Mod+K" },
    context: "timeline",
    labelKey: "cmd.track.cycle_kind",
  },
  {
    id: "track.group_into_bus",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.track.group_into_bus",
  },
  {
    id: "track.new_bus",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.track.new_bus",
  },
  {
    id: "group.toggle",
    keys: { mac: ["E", "Mod+G"], other: ["E", "Mod+G"] },
    context: "timeline",
    labelKey: "cmd.group.toggle",
  },
  {
    id: "bus.collapse",
    keys: { mac: "Alt+Mod+ArrowLeft", other: "Alt+Mod+ArrowLeft" },
    context: "timeline",
    labelKey: "cmd.bus.collapse",
  },
  {
    id: "bus.expand",
    keys: { mac: "Alt+Mod+ArrowRight", other: "Alt+Mod+ArrowRight" },
    context: "timeline",
    labelKey: "cmd.bus.expand",
  },
  {
    id: "bus.mute",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.bus.mute",
  },
  {
    id: "bus.ungroup",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.bus.ungroup",
  },
  {
    id: "track.remove_from_bus",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.track.remove_from_bus",
  },
  {
    id: "sync.mark",
    keys: { mac: ["Y", "Alt+Mod+S"], other: ["Y", "Alt+Mod+S"] },
    context: "timeline",
    labelKey: "cmd.sync.mark",
  },
  {
    id: "sync.resync",
    keys: { mac: ["R", "Alt+Mod+R"], other: ["R", "Alt+Mod+R"] },
    context: "timeline",
    labelKey: "cmd.sync.resync",
  },
  {
    id: "sync.point1",
    keys: { mac: "Alt+Mod+1", other: "Alt+Mod+1" },
    context: "timeline",
    labelKey: "cmd.sync.point1",
  },
  {
    id: "sync.point2",
    keys: { mac: "Alt+Mod+2", other: "Alt+Mod+2" },
    context: "timeline",
    labelKey: "cmd.sync.point2",
  },
  {
    id: "sync.resync_end",
    keys: { mac: "Shift+Alt+Mod+R", other: "Shift+Alt+Mod+R" },
    context: "timeline",
    labelKey: "cmd.sync.resync_end",
  },
  // Candidates (WP18). ] [ D and Shift+Mod+D work from every panel (none is a typing key);
  // Enter, K and Shift+Space only while the Candidates tab has the keyboard.
  {
    id: "candidate.mark",
    keys: { mac: "D", other: "D" },
    context: "global",
    labelKey: "cmd.candidate.mark",
  },
  {
    id: "candidate.mark_range",
    keys: { mac: "Alt+D", other: "Alt+D" },
    context: "timeline",
    labelKey: "cmd.candidate.mark_range",
  },
  {
    id: "candidate.next",
    keys: { mac: ["]", "Alt+ArrowDown"], other: ["]", "Alt+ArrowDown"] },
    context: "global",
    labelKey: "cmd.candidate.next",
  },
  {
    id: "candidate.previous",
    keys: { mac: ["[", "Alt+ArrowUp"], other: ["[", "Alt+ArrowUp"] },
    context: "global",
    labelKey: "cmd.candidate.previous",
  },
  {
    id: "candidate.apply",
    keys: { mac: ["Backspace", "Delete"], other: ["Backspace", "Delete"] },
    context: "candidates",
    labelKey: "cmd.candidate.apply",
  },
  {
    id: "candidate.apply_ripple",
    keys: { mac: null, other: null },
    context: "candidates",
    labelKey: "cmd.candidate.apply_ripple",
  },
  {
    id: "candidate.reject",
    keys: { mac: "Enter", other: "Enter" },
    context: "candidates",
    labelKey: "cmd.candidate.reject",
  },
  {
    id: "candidate.preview",
    keys: { mac: "Shift+Space", other: "Shift+Space" },
    context: "candidates",
    labelKey: "cmd.candidate.preview",
  },
  {
    id: "candidate.filter",
    keys: { mac: "Shift+Mod+D", other: "Shift+Mod+D" },
    context: "global",
    labelKey: "cmd.candidate.filter",
  },
  {
    id: "candidate.find",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.candidate.find",
  },
  {
    id: "transcript.delete_words",
    keys: { mac: ["Backspace", "Delete"], other: ["Backspace", "Delete"] },
    context: "transcript",
    labelKey: "cmd.transcript.delete_words",
  },
  {
    id: "transcript.remove_words",
    keys: { mac: "X", other: "X" },
    context: "transcript",
    labelKey: "cmd.transcript.remove_words",
  },
  {
    id: "transcript.cut_words",
    keys: { mac: "Mod+X", other: "Mod+X" },
    context: "transcript",
    labelKey: "cmd.transcript.cut_words",
  },
  {
    id: "transcript.correct",
    keys: { mac: "Enter", other: "Enter" },
    context: "transcript",
    labelKey: "cmd.transcript.correct",
  },
  {
    id: "transcript.mark_candidate",
    keys: { mac: "Alt+D", other: "Alt+D" },
    context: "transcript",
    labelKey: "cmd.transcript.mark_candidate",
  },
  {
    id: "transcript.find",
    keys: { mac: "Mod+F", other: "Mod+F" },
    context: "global",
    labelKey: "cmd.transcript.find",
  },
  { id: "spot", keys: { mac: "Mod+J", other: "Mod+J" }, context: "global", labelKey: "cmd.spot" },
  { id: "rename", keys: { mac: "F2", other: "F2" }, context: "global", labelKey: "cmd.rename" },
  {
    id: "app.import",
    keys: { mac: "Mod+I", other: "Mod+I" },
    context: "global",
    labelKey: "cmd.app.import",
  },
  {
    id: "app.export",
    keys: { mac: "Mod+E", other: "Mod+E" },
    context: "global",
    labelKey: "cmd.app.export",
  },
  {
    id: "marker.add",
    keys: { mac: "Mod+Enter", other: "Mod+Enter" },
    context: "global",
    labelKey: "cmd.marker.add",
  },
  {
    id: "region.from_selection",
    keys: { mac: "Alt+M", other: "Alt+M" },
    context: "global",
    labelKey: "cmd.region.from_selection",
  },
  {
    id: "marker.next",
    keys: { mac: "Shift+Mod+ArrowRight", other: "Shift+Mod+ArrowRight" },
    context: "global",
    labelKey: "cmd.marker.next",
  },
  {
    id: "marker.prev",
    keys: { mac: "Shift+Mod+ArrowLeft", other: "Shift+Mod+ArrowLeft" },
    context: "global",
    labelKey: "cmd.marker.prev",
  },
  {
    id: "marker.delete",
    keys: { mac: "Shift+Alt+M", other: "Shift+Alt+M" },
    context: "global",
    labelKey: "cmd.marker.delete",
  },
  // Narration placeholders (WP43): T adds script text at the play cursor, Enter edits the
  // selected one on the timeline, Shift+Alt+T deletes it; Take and the script export are
  // in the menu and the palette.
  {
    id: "placeholder.add",
    keys: { mac: "T", other: "T" },
    context: "global",
    labelKey: "cmd.placeholder.add",
  },
  {
    id: "placeholder.edit",
    keys: { mac: "Enter", other: "Enter" },
    context: "timeline",
    labelKey: "cmd.placeholder.edit",
  },
  {
    id: "placeholder.take",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.placeholder.take",
  },
  {
    id: "placeholder.delete",
    keys: { mac: "Shift+Alt+T", other: "Shift+Alt+T" },
    context: "global",
    labelKey: "cmd.placeholder.delete",
  },
  {
    id: "export.narration_script_txt",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.export.narration_script_txt",
  },
  {
    id: "export.narration_script_md",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.export.narration_script_md",
  },
  {
    id: "export.subtitles_srt",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.export.subtitles_srt",
  },
  {
    id: "export.subtitles_vtt",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.export.subtitles_vtt",
  },
  {
    id: "export.transcript_txt",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.export.transcript_txt",
  },
  {
    id: "export.transcript_md",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.export.transcript_md",
  },
  {
    id: "export.chapters_text",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.export.chapters_text",
  },
  {
    id: "export.chapters_json",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.export.chapters_json",
  },
  // The plan's Tracks key (WP11); Mod+E is the Mix export's, not built yet.
  {
    id: "export.tracks",
    keys: { mac: "Shift+Alt+Mod+E", other: "Shift+Alt+Mod+E" },
    context: "global",
    labelKey: "cmd.export.tracks",
  },
  // The same export without the folder question (no key by default).
  {
    id: "export.tracks_quick",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.export.tracks_quick",
  },
  // One mix and one all-tracks command per export format (File menu submenus); no keys.
  ...EXPORT_FORMAT_IDS.flatMap((format) =>
    ["mix", "tracks"].map((what) => ({
      id: `export.${what}_${format}`,
      keys: { mac: null, other: null },
      context: "global",
      labelKey: `cmd.export.${what}_${format}`,
    })),
  ),
  {
    id: "export.automix",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.export.automix",
  },
  {
    id: "export.regions",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.export.regions",
  },
  {
    id: "app.save",
    keys: { mac: "Mod+S", other: "Mod+S" },
    context: "global",
    labelKey: "cmd.app.save",
  },
  {
    id: "app.save_named",
    keys: { mac: "Shift+Mod+S", other: "Shift+Mod+S" },
    context: "global",
    labelKey: "cmd.app.save_named",
  },
  {
    id: "app.transcribe",
    keys: { mac: "Shift+Mod+I", other: "Shift+Mod+I" },
    context: "global",
    labelKey: "cmd.app.transcribe",
  },
  {
    id: "app.automix",
    keys: { mac: "Mod+L", other: "Mod+L" },
    context: "global",
    labelKey: "cmd.app.automix",
  },
  {
    id: "gate.open_stretch",
    keys: { mac: null, other: null },
    context: "timeline",
    labelKey: "cmd.gate.open_stretch",
  },
  {
    id: "app.auto_silence",
    keys: { mac: "Alt+Mod+P", other: "Alt+Mod+P" },
    context: "global",
    labelKey: "cmd.app.auto_silence",
  },
  {
    id: "palette.open",
    keys: { mac: "Mod+K", other: "Mod+K" },
    context: "text-field",
    labelKey: "cmd.palette.open",
  },
  {
    id: "help.open",
    keys: { mac: "F1", other: "F1" },
    context: "text-field",
    labelKey: "cmd.help.open",
  },
  { id: "help.keys", keys: { mac: "?", other: "?" }, context: "global", labelKey: "cmd.help.keys" },
  {
    id: "keymap.import",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.keymap.import",
  },
  {
    id: "keymap.export",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.keymap.export",
  },
  {
    id: "view.fit_tracks",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.view.fit_tracks",
  },
  {
    id: "view.auto_fit_tracks",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.view.auto_fit_tracks",
  },
  {
    id: "view.collapse_all_buses",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.view.collapse_all_buses",
  },
  {
    id: "view.expand_all_buses",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.view.expand_all_buses",
  },
  {
    id: "view.reset_remembered",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.view.reset_remembered",
  },
  {
    id: "view.pause_1_5",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.view.pause_1_5",
  },
  {
    id: "view.pause_3",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.view.pause_3",
  },
  {
    id: "view.pause_6",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.view.pause_6",
  },
  {
    id: "view.pause_never",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.view.pause_never",
  },
  {
    id: "keymap.reset",
    keys: { mac: null, other: null },
    context: "global",
    labelKey: "cmd.keymap.reset",
  },
];

// The status bar shows at most three hints for the focused panel: the first three
// of these whose command exists (a planned command is not hinted until it lands).
// `hintKey` is the short word shown beside the key.
export const STATUS_HINTS = {
  timeline: [
    { id: "transport.play", hintKey: "ui.hint.play" },
    { id: "view.toggle", hintKey: "ui.hint.view" },
    { id: "edit.split", hintKey: "ui.hint.split" },
    { id: "edit.remove", hintKey: "ui.hint.cut" },
    { id: "panel.next", hintKey: "ui.hint.panels" },
  ],
  transcript: [
    { id: "transport.play", hintKey: "ui.hint.play" },
    { id: "transcript.delete_words", hintKey: "ui.hint.delete_words" },
    { id: "transcript.remove_words", hintKey: "ui.hint.cut_words" },
    { id: "transcript.find", hintKey: "ui.hint.find" },
    { id: "panel.next", hintKey: "ui.hint.panels" },
    { id: "nav.home", hintKey: "ui.hint.home" },
  ],
  candidates: [
    { id: "candidate.apply", hintKey: "ui.hint.candidate_delete" },
    { id: "candidate.reject", hintKey: "ui.hint.candidate_keep" },
    { id: "candidate.next", hintKey: "ui.hint.candidate_next" },
    { id: "candidate.preview", hintKey: "ui.hint.candidate_preview" },
    { id: "panel.next", hintKey: "ui.hint.panels" },
  ],
  side: [
    { id: "transport.play", hintKey: "ui.hint.play" },
    { id: "panel.next", hintKey: "ui.hint.panels" },
    { id: "nav.home", hintKey: "ui.hint.home" },
  ],
};
