// The Edit | Rendered mix switch (transport corner), the banner over the lanes while the
// rendered mix plays, and the dimmed track controls (they do not affect the file). What each
// shows is render-listen-model.js; this file only draws and wires. The markup is in
// index.html (#render-ab, #render-banner).

import { leftStaleRender, renderBanner, renderSwitch } from "./render-listen-model.js";

/**
 * `listen(on)` -> Promise asks the server; `formatWhen(iso)` writes a time (Helsinki, zone
 * named); `rate()` the project rate; `notice(text)` shows the stale notice.
 * Returns { update(state) }.
 */
export function createRenderListenView({ t, listen, formatWhen, rate, notice, doc = document }) {
  const $ = (id) => doc.getElementById(id);
  const group = $("render-ab");
  const edit = $("render-edit");
  const mix = $("render-mix");
  const banner = $("render-banner");
  const bannerText = $("render-banner-text");
  const back = $("render-back");
  const heads = $("track-headers");
  let last = null;

  edit?.addEventListener("click", () => {
    if (edit.getAttribute("aria-pressed") !== "true") void listen(false);
  });
  mix?.addEventListener("click", () => {
    if (mix.getAttribute("aria-disabled") === "true") return; // its title says why
    if (mix.getAttribute("aria-pressed") !== "true") void listen(true);
  });
  back?.addEventListener("click", () => void listen(false));

  return {
    update(state) {
      const render = state.render ?? null;
      const ab = renderSwitch(render, t);
      if (group) group.hidden = !ab.visible;
      if (edit && mix) {
        edit.setAttribute("aria-pressed", String(ab.editPressed));
        mix.setAttribute("aria-pressed", String(ab.mixPressed));
        // aria-disabled, not disabled: the tooltip saying why must still show on hover.
        mix.setAttribute("aria-disabled", String(ab.mixDisabled && !ab.mixPressed));
        edit.title = ab.editTitle;
        mix.title = ab.mixTitle;
      }
      const shown = renderBanner(render, rate(), t, formatWhen);
      if (banner) {
        banner.hidden = !shown.visible;
        banner.title = shown.title;
      }
      if (bannerText) bannerText.textContent = shown.text;
      if (heads) {
        heads.classList.toggle("render-listening", shown.visible);
        if (shown.visible) heads.title = t("ui.render.controls_title");
        else heads.removeAttribute("title");
      }
      if (leftStaleRender(last, render)) notice(t("ui.render.stale_notice"));
      last = render;
    },
  };
}
