import { enhanceDialog } from "./dialog-keys.js";

/** Historical contents remain provisional until a row's explicit restore button is pressed. */
export function createPartVersionsDialog({ t, api, apply, notice }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet automix-dialog";
  const title = document.createElement("h2");
  title.id = "part-versions-title";
  title.textContent = t("cmd.history.part_versions");
  dialog.setAttribute("aria-labelledby", title.id);
  const status = document.createElement("p");
  status.setAttribute("role", "status");
  const list = document.createElement("div");
  const more = button("ui.part_versions.more", () => render());
  const close = button("ui.part_versions.close", () => dialog.close());
  close.dataset.dialogCancel = "";
  const stop = button("ui.part_versions.stop", () => void api.stopClipboardPreview().catch(fail));
  const footer = document.createElement("div");
  footer.className = "cheatsheet-footer";
  footer.append(stop, close);
  dialog.append(title, status, list, more, footer);
  document.body.append(dialog);
  enhanceDialog(dialog, { t });
  let rows = [];
  let shown = 0;
  let query = null;
  let generation = 0;

  function button(key, run) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = "button";
    element.textContent = t(key);
    element.addEventListener("click", run);
    return element;
  }
  function fail(error) {
    status.textContent = error.message;
  }
  function render() {
    const page = rows.slice(shown, shown + 8);
    shown += page.length;
    more.hidden = shown >= rows.length;
    for (const row of page) {
      const section = document.createElement("section");
      section.className = "form-row";
      const label = document.createElement("p");
      label.textContent = t("ui.part_versions.row", {
        names: row.names.join(", ") || t("ui.part_versions.silence"),
        first_created: row.first_created,
        created: row.created,
        seconds: ((query.end - query.start) / query.rate).toFixed(2),
        current: row.current ? t("ui.part_versions.current") : "",
      });
      const canvas = document.createElement("canvas");
      canvas.width = 240;
      canvas.height = 40;
      canvas.setAttribute("aria-label", t("ui.part_versions.waveform"));
      const body = { ...query, node: row.node, expected_head: row.head };
      const play = button(
        "ui.part_versions.play",
        () => void api.previewPartVersion(body).catch(fail),
      );
      play.disabled = row.clips.length === 0;
      const restore = button("ui.part_versions.restore", async () => {
        restore.disabled = true;
        try {
          await api.stopClipboardPreview();
          apply(await api.restorePartVersion(body));
          notice(t("history.restore_part"));
          dialog.close();
        } catch (error) {
          fail(error);
          restore.disabled = false;
        }
      });
      restore.disabled = row.current;
      section.append(label, canvas, play, restore);
      list.append(section);
      void thumbnail(canvas, row.clips, query.end - query.start).catch(() => {
        canvas.setAttribute("aria-label", t("ui.part_versions.no_waveform"));
      });
    }
  }
  dialog.addEventListener("close", () => {
    generation++;
    void api.stopClipboardPreview().catch(() => {});
  });
  return {
    async open(range, rate) {
      if (dialog.open) dialog.close();
      const token = ++generation;
      query = { ...range, rate };
      rows = [];
      shown = 0;
      list.replaceChildren();
      more.hidden = true;
      status.textContent = t("ui.part_versions.loading");
      dialog.showModal();
      try {
        const response = await api.partVersions(range);
        if (token !== generation || !dialog.open) return;
        rows = response.versions;
        status.textContent = t(rows.length ? "ui.part_versions.note" : "ui.part_versions.empty");
        render();
      } catch (error) {
        if (token === generation) fail(error);
      }
    },
  };
}

/** Thumbnails reuse immutable peak tiles; no media is decoded in the browser. */
async function thumbnail(canvas, clips, span) {
  const context = canvas.getContext("2d");
  context.strokeStyle = getComputedStyle(canvas).color;
  const levels = [256, 1024, 4096, 16384, 65536];
  const level = levels.find((value) => value >= span / canvas.width) ?? levels.at(-1);
  for (const clip of clips) {
    const first = Math.floor(clip.offset / level);
    const last = Math.ceil((clip.offset + clip.length) / level);
    for (let tile = Math.floor(first / 1024); tile <= Math.floor((last - 1) / 1024); tile++) {
      const response = await fetch(`/api/peaks/${encodeURIComponent(clip.media)}/${level}/${tile}`);
      if (!response.ok) throw new Error();
      const peaks = new Float32Array(await response.arrayBuffer());
      context.beginPath();
      for (
        let peak = Math.max(first, tile * 1024);
        peak < Math.min(last, (tile + 1) * 1024);
        peak++
      ) {
        const index = (peak - tile * 1024) * 2;
        const x = ((clip.start + peak * level - clip.offset) / span) * canvas.width;
        context.moveTo(x, 20 - peaks[index] * 18);
        context.lineTo(x, 20 - peaks[index + 1] * 18);
      }
      context.stroke();
    }
  }
}
