// Listening to the rendered mix (owner, 2026-10-21): the pure parts. The server says what
// render the project remembers (state.render: available, current, missing, reason,
// listening, name, range, set_at; src/kuulas/render_listen.py); these functions say what
// the Edit | Rendered mix switch, the banner and the automix dialog's range box show.
// app.js draws them.

/** A range shorter than this is not worth an automixer run (and the UI says so). */
export const MIN_RANGE_SECONDS = 1;

/** "mm:ss-mm:ss" of [start, end] frames (whole seconds; minutes are not wrapped at 60). */
export function spanText(range, rate) {
  const one = (frame) => {
    const seconds = Math.floor(frame / rate);
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`;
  };
  return `${one(range[0])}-${one(range[1])}`;
}

/**
 * When a render was made, for the banner: its Helsinki date ("21.10.") and `timeText`
 * (i18n's formatAbsoluteTime: the clock with the zone named).
 */
export function renderWhen(iso, timeText) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Helsinki",
    day: "numeric",
    month: "numeric",
  }).formatToParts(new Date(iso));
  const part = (type) => parts.find((p) => p.type === type)?.value ?? "";
  return `${part("day")}.${part("month")}. ${timeText}`;
}

/**
 * The switch in the transport corner: { visible, editPressed, mixPressed, mixDisabled,
 * editTitle, mixTitle }. Only while the project remembers a render; its "Rendered mix"
 * side is disabled, saying why, while the render no longer matches the edit.
 */
export function renderSwitch(render, t) {
  if (!render?.available) {
    return {
      visible: false,
      editPressed: true,
      mixPressed: false,
      mixDisabled: true,
      editTitle: "",
      mixTitle: "",
    };
  }
  const listening = render.listening === true;
  let mixTitle = t("ui.render.mix_title", { name: render.name ?? "" });
  if (!render.current) {
    mixTitle =
      render.reason === "edited"
        ? t("ui.render.stale_title")
        : t("ui.render.missing_title", { name: render.name ?? "" });
  }
  return {
    visible: true,
    editPressed: !listening,
    mixPressed: listening,
    mixDisabled: !render.current,
    editTitle: t("ui.render.edit_title"),
    mixTitle,
  };
}

/**
 * The banner above the lanes while the rendered mix plays: { visible, text, title }.
 * `formatWhen(iso)` writes the render's time (Helsinki, zone named). The title is the
 * level note: the file is mastered, so it is louder than the edit.
 */
export function renderBanner(render, rate, t, formatWhen) {
  if (!render?.listening) return { visible: false, text: "", title: "" };
  let text = t("ui.render.banner", {
    name: render.name ?? "",
    when: render.set_at ? formatWhen(render.set_at) : "",
  });
  if (Array.isArray(render.range)) {
    text += `, ${t("ui.render.banner_range", { span: spanText(render.range, rate) })}`;
  }
  return { visible: true, text, title: t("ui.render.banner_title") };
}

/**
 * Did listening end because the render went stale (an edit, an undo past the render)?
 * Then the app says "The edit changed after the render: back to the edit." `Back to
 * the edit` itself (still current) says nothing.
 */
export function leftStaleRender(before, after) {
  if (!before?.listening || after?.listening) return false;
  return !after?.current;
}

/**
 * The automix dialog's "Only the In/Out range" box: { enabled, range }. Enabled with both
 * marks set, the range longer than MIN_RANGE_SECONDS and shorter than the project.
 */
export function rangeChoice({ inPoint, outPoint, length, rate }) {
  const off = { enabled: false, range: null };
  if (!Number.isFinite(inPoint) || !Number.isFinite(outPoint)) return off;
  const start = Math.round(Math.max(0, Math.min(inPoint, outPoint)));
  const end = Math.round(Math.max(inPoint, outPoint));
  const span = end - start;
  if (span <= MIN_RANGE_SECONDS * rate || span >= length) return off;
  return { enabled: true, range: [start, end] };
}

/**
 * The automix dialog's "Only the selection" choice from a resolved export selection
 * (export-selection-model.js): { enabled, range, trackIds, names }. Enabled when the span is
 * longer than MIN_RANGE_SECONDS; a null `trackIds` is all tracks.
 */
export function selectionChoice(selection, { length, rate }) {
  const off = { enabled: false, range: null };
  if (!selection) return off;
  const [start, end] = selection.range;
  if (end - start <= MIN_RANGE_SECONDS * rate || end - start > length) return off;
  return {
    enabled: true,
    range: [start, end],
    trackIds: selection.trackIds,
    names: selection.names,
  };
}

/** The run body with `range` (and `track_ids` when only some tracks) while the box is ticked ("1") and the range is allowed. */
export function withRange(body, onlyRange, choice) {
  if (!onlyRange || !choice?.enabled) return body;
  return {
    ...body,
    range: choice.range,
    ...(choice.trackIds ? { track_ids: choice.trackIds } : {}),
  };
}
