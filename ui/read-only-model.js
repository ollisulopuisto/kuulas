// The banner of a project that is open read-only because another window or machine holds it
// (package.py lock; /api/state says who). Pure: the message key and its values, no DOM.

/**
 * `note` is the state's read_only ({ host, user, opened_utc }) or null for a project you can
 * edit. Returns { key, values } for t(), or null. The time carries its zone ("14.05 GMT+3"),
 * in the viewer's own zone unless `timeZone` says otherwise (tests).
 */
export function readOnlyBanner(note, { locale, timeZone } = {}) {
  if (!note) return null;
  const opened = new Date(note.opened_utc);
  const since = Number.isNaN(opened.getTime())
    ? null
    : new Intl.DateTimeFormat(locale, {
        hour: "2-digit",
        minute: "2-digit",
        timeZone,
        timeZoneName: "short",
      }).format(opened);
  const host = note.host || "?";
  if (since === null) return { key: "ui.readonly.banner_no_time", values: { host } };
  if (!note.user) return { key: "ui.readonly.banner_no_user", values: { host, since } };
  return { key: "ui.readonly.banner", values: { user: note.user, host, since } };
}
