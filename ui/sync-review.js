// Full-window, isolated timing review. Only this surface receives keys while open.
// Every change is acknowledged by the server before another move or audition.
import * as api from "./api.js";
import { frameToTime } from "./format.js";
import { auditionRange, moveRequest, selectedTrackIds, timingStatus } from "./sync-review-model.js";
import { createTileStore } from "./tiles.js";
import { columnsFromTiles, pickLevel, waveformColumns } from "./waveform.js";

export function createSyncReview({ t, getState, refresh, notice, doc = document }) {
  let review = null;
  let root = null;
  let busy = false;
  let selected = null;
  let scope = "track";
  let method = "auto";
  let frame = 0;
  let zoom = 1;
  let timer = null;
  let job = null;
  let loop = false;
  let previousFocus = null;
  let activeDrag = false;
  let playbackTimer = null;
  let playing = false;
  let listening = { original: false, continuous: false };
  let errorText = "";
  let controls = null;
  const tiles = createTileStore({
    fetchTile: api.peakTile,
    onChange: () => {
      if (review && !busy && !activeDrag) draw();
    },
  });
  const ns = "http://www.w3.org/2000/svg";
  const request = async (path, body) => {
    const response = await fetch(
      `/api/sync-review${path}`,
      body == null
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.text ?? response.statusText);
    return result;
  };
  const text = (key, params) => t(`ui.sync_review.${key}`, params);
  function element(tag, value = "", parent = root) {
    const node = doc.createElement(tag);
    if (value) node.textContent = value;
    parent?.append(node);
    return node;
  }
  function button(key, action, parent = root) {
    const node = doc.createElement("button");
    node.className = "button secondary";
    node.textContent = text(key);
    parent.append(node);
    node.type = "button";
    node.className = "button secondary";
    node.disabled = busy;
    node.addEventListener("click", () => void perform(action));
    return node;
  }
  function reportError(message) {
    if (!root) {
      notice(message);
      return;
    }
    errorText = String(message);
    let alert = root.querySelector("[role=alert]");
    if (!alert) {
      alert = element("p", "", root);
      alert.setAttribute("role", "alert");
    }
    alert.textContent = errorText;
    alert.className = "sync-review-error";
  }
  async function perform(action) {
    if (busy) return;
    busy = true;
    root?.setAttribute("aria-busy", "true");
    try {
      await action();
    } catch (error) {
      reportError(error.message);
    } finally {
      busy = false;
      if (review) draw();
    }
  }
  function length() {
    return Math.max(
      1,
      ...review.project.tracks.flatMap((tr) => tr.clips.map((c) => c.start + c.length)),
    );
  }
  function chosen() {
    for (const track of review.project.tracks) {
      const clip = track.clips.find((c) => c.id === selected);
      if (clip) return { track, clip };
    }
    return null;
  }
  async function move(delta) {
    const pick = chosen();
    if (!pick || pick.track.id === review.anchor) return;
    await stop();
    review = await request(
      "/move",
      moveRequest(review, pick.track.id, pick.clip.id, Math.round(delta), scope),
    );
  }
  async function listen(original = false, continuous = false) {
    const range = continuous
      ? { at: frame, seconds: (length() - frame) / review.project.rate }
      : auditionRange(frame, length(), review.project.rate);
    await request("/listen", { id: review.id, original, loop, ...range });
    listening = { original, continuous };
    playing = true;
    clearTimeout(playbackTimer);
    playbackTimer = setTimeout(playbackPosition, 150);
  }
  async function playbackPosition() {
    if (!review) return;
    try {
      const status = await api.getTransport();
      if (!review) return;
      playing = status.playing === true;
      frame = status.position ?? frame;
      const line = root.querySelector(".sync-playhead");
      const svg = line?.ownerSVGElement;
      if (svg) {
        const x = 185 + (frame - Number(svg.dataset.origin)) / Number(svg.dataset.scale);
        line.setAttribute("x1", x);
        line.setAttribute("x2", x);
      }
      const clock = root.querySelector(".sync-review-clock");
      if (clock) clock.textContent = frameToTime(frame, review.project.rate);
      if (playing) playbackTimer = setTimeout(playbackPosition, 150);
    } catch (error) {
      reportError(error.message);
    }
  }
  async function stop() {
    clearTimeout(playbackTimer);
    playing = false;
    await api.transport("stop");
  }
  async function seek(at) {
    frame = at;
    if (playing) {
      clearTimeout(playbackTimer);
      // A seek can leave a six-second audition or its loop. Rebuild the
      // listening range at the new position, keeping original/proposal mode.
      await listen(listening.original, listening.continuous);
    }
  }
  function svgNode(tag, attrs, parent) {
    const node = doc.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
    parent.append(node);
    return node;
  }
  function wave(svg, clip, x, width, y, height, framesPerPixel, color) {
    const visibleX = Math.max(x, 180);
    const visibleEnd = Math.min(x + width, root.clientWidth - 45);
    if (visibleEnd <= visibleX) return;
    const count = Math.ceil(visibleEnd - visibleX);
    const level = pickLevel(framesPerPixel);
    const { data, missing } = columnsFromTiles({
      lookup: (tile) => tiles.lookup(clip.media, level, tile),
      level,
      startFrame: clip.offset + (visibleX - x) * framesPerPixel,
      framesPerPixel,
      count,
    });
    tiles.want(missing.map((tile) => ({ media: clip.media, level, tile })));
    const bars = waveformColumns(data, "full", "db", height);
    let path = "";
    for (let i = 0; i < count; i += 2)
      path += `M${visibleX + i},${y + bars[2 * i]}V${y + bars[2 * i + 1]}`;
    svgNode("path", { d: path, stroke: color, "stroke-width": 1, "pointer-events": "none" }, svg);
  }
  function drawTimeline(parent) {
    const pane = element("div", "", parent);
    pane.className = "sync-review-lanes";
    const width = Math.max(600, root.clientWidth - 55);
    const height = Math.max(230, review.tracks.length * 120 + 45);
    const svg = svgNode(
      "svg",
      { width, height, role: "img", "aria-label": text("timeline") },
      pane,
    );
    const rate = review.project.rate;
    const visible = Math.max(rate, length() / zoom);
    const origin = Math.max(0, Math.min(length() - visible, frame - visible / 2));
    const scale = visible / (width - 210);
    svg.dataset.origin = origin;
    svg.dataset.scale = scale;
    const xOf = (at) => 185 + (at - origin) / scale;
    const valueAt = (event) =>
      Math.max(
        0,
        Math.min(
          length() - 1,
          Math.round(origin + (event.clientX - svg.getBoundingClientRect().left - 185) * scale),
        ),
      );
    for (let i = 0; i <= 6; i++) {
      const at = origin + (i * visible) / 6;
      svgNode("line", { x1: xOf(at), x2: xOf(at), y1: 30, y2: height, class: "sync-grid" }, svg);
      const label = svgNode(
        "text",
        { x: Math.min(xOf(at), width - 75), y: 22, class: "sync-time" },
        svg,
      );
      label.textContent = frameToTime(Math.round(at), rate);
    }
    svg.addEventListener("pointerdown", (event) => {
      if (event.target !== svg && event.target.tagName !== "line") return;
      void perform(() => seek(valueAt(event)));
    });
    let index = 0;
    for (const track of review.project.tracks.filter((tr) => review.tracks.includes(tr.id))) {
      const y = 45 + index * 120;
      const row = review.result?.tracks?.find((item) => item.track === track.id);
      const title = svgNode("text", { x: 8, y: y + 23, class: "sync-name" }, svg);
      title.textContent = track.name;
      const subtitle = svgNode("text", { x: 8, y: y + 49, class: "sync-time" }, svg);
      subtitle.textContent =
        track.id === review.anchor
          ? review.result?.anchor_status
            ? text(`status.${review.result.anchor_status}`)
            : text("anchor")
          : text(`status.${timingStatus(review, track, row)}`);
      const color = track.id === review.anchor ? "var(--track-0-wave)" : "var(--accent-text)";
      for (const clip of track.clips) {
        const x = xOf(clip.start),
          w = clip.length / scale;
        if (x + w < 185 || x > width) continue;
        const group = svgNode("g", { "data-track": track.id }, svg);
        const rect = svgNode(
          "rect",
          {
            x: Math.max(185, x),
            y,
            width: Math.max(1, Math.min(width, x + w) - Math.max(185, x)),
            height: 75,
            rx: 4,
            class: clip.id === selected ? "sync-clip selected" : "sync-clip",
            tabindex: 0,
            role: "button",
            "aria-label": `${track.name}: ${clip.name || clip.id}`,
            "data-clip": clip.id,
          },
          group,
        );
        wave(group, clip, x, w, y + 4, 67, scale, color);
        rect.addEventListener("focus", () => {
          selected = clip.id;
          for (const piece of svg.querySelectorAll("[data-clip]"))
            piece.classList.toggle("selected", piece === rect);
          drawControls();
        });
        rect.addEventListener("pointerdown", (event) => {
          if (busy) return;
          if (track.id === review.anchor) {
            void perform(() => seek(valueAt(event)));
            return;
          }
          event.preventDefault();
          selected = clip.id;
          activeDrag = true;
          const startX = event.clientX;
          rect.setPointerCapture(event.pointerId);
          rect.addEventListener("pointermove", drag);
          rect.addEventListener("pointerup", release, { once: true });
          rect.addEventListener("pointercancel", cancel, { once: true });
          function drag(e) {
            const dx = e.clientX - startX;
            const groups =
              scope === "track"
                ? [...svg.querySelectorAll("g[data-track]")].filter(
                    (g) => g.dataset.track === track.id,
                  )
                : [group];
            for (const item of groups) item.setAttribute("transform", `translate(${dx},0)`);
          }
          function cancel() {
            activeDrag = false;
            rect.removeEventListener("pointermove", drag);
            draw();
          }
          function release(e) {
            activeDrag = false;
            rect.removeEventListener("pointermove", drag);
            frame = valueAt(e);
            const delta = Math.round((e.clientX - startX) * scale);
            if (Math.abs(e.clientX - startX) < 3) {
              void perform(() => seek(frame));
              return;
            }
            void perform(() => move(delta));
          }
        });
      }
      index++;
    }
    svgNode(
      "line",
      {
        x1: xOf(frame),
        x2: xOf(frame),
        y1: 30,
        y2: height,
        class: "sync-playhead",
        "pointer-events": "none",
      },
      svg,
    );
  }
  function draw() {
    if (!review || !root) return;
    const focusedClip = root.contains(doc.activeElement) ? doc.activeElement?.dataset?.clip : null;
    root.replaceChildren();
    root.setAttribute("aria-busy", String(busy));
    const banner = element("header");
    banner.className = "sync-review-banner";
    const title = element("div", "", banner);
    element("h1", text("title"), title);
    element("p", text("intro"), title);
    button("cancel", () => close(false), banner);
    const accept = button("apply", () => close(true), banner);
    accept.className = "button primary";
    const tools = element("div");
    tools.className = "sync-review-tools";
    const methods = element("select", "", tools);
    methods.setAttribute("aria-label", text("method"));
    for (const value of ["auto", "sound", "gaps"]) {
      const option = element("option", text(value), methods);
      option.value = value;
    }
    methods.value = method;
    methods.disabled = busy || Boolean(job);
    methods.addEventListener("change", () => {
      method = methods.value;
    });
    button("calculate", measure, tools).disabled = busy || Boolean(job);
    button("play", () => (playing ? stop() : listen(false, true)), tools);
    button("stop", stop, tools);
    button(
      "zoom_in",
      () => {
        zoom = Math.min(512, zoom * 2);
      },
      tools,
    );
    button(
      "zoom_out",
      () => {
        zoom = Math.max(1, zoom / 2);
      },
      tools,
    );
    button(
      "loop",
      () => {
        loop = !loop;
      },
      tools,
    ).setAttribute("aria-pressed", String(loop));
    element("span", frameToTime(frame, review.project.rate), tools).className = "sync-review-clock";
    if (errorText) reportError(errorText);
    const status = element("p", job ? text("analyzing") : text("pieces"));
    status.setAttribute("role", "status");
    drawTimeline(root);
    controls = element("footer");
    controls.className = "sync-review-controls";
    drawControls();
    if (focusedClip)
      [...root.querySelectorAll("[data-clip]")]
        .find((node) => node.dataset.clip === focusedClip)
        ?.focus();
    const results = element("div");
    results.className = "sync-review-results";
    for (const row of review.result?.tracks ?? []) {
      const track = review.project.tracks.find((tr) => tr.id === row.track);
      const line = element("div", "", results);
      element(
        "strong",
        `${track?.name ?? row.track} · ${text(row.method)} · ${text(`status.${timingStatus(review, track, row)}`)}`,
        line,
      );
      if (row.fit?.slope && Math.abs(row.fit.slope) >= 1e-6)
        element("span", text("drift", { ppm: Math.round(row.fit.slope * 1e6) }), line);
      for (const [i, option] of (row.options ?? []).entries()) {
        const btn = button(
          "alternative",
          async () => {
            selected = track.clips[0].id;
            review = await request("/move", {
              id: review.id,
              track: row.track,
              frames:
                Math.round(option.delta * review.project.rate) - (review.offsets[selected] ?? 0),
            });
            const updated = review.result?.tracks?.find((item) => item.track === row.track);
            if (updated) updated.auditions = option.auditions;
          },
          line,
        );
        btn.textContent = text("alternative_value", {
          number: i + 1,
          seconds: option.delta.toFixed(3),
        });
      }
      for (const [key, fraction] of [
        ["beginning", 0.1],
        ["middle", 0.5],
        ["end", 0.9],
      ]) {
        button(
          key,
          async () => {
            const point = row.auditions?.[[0.1, 0.5, 0.9].indexOf(fraction)];
            frame = Math.round(point == null ? length() * fraction : point * review.project.rate);
            await listen(false);
          },
          line,
        );
      }
    }
  }
  function drawControls() {
    controls.replaceChildren();
    const pick = chosen();
    if (pick && pick.track.id !== review.anchor) {
      element("strong", pick.track.name, controls);
      const select = element("select", "", controls);
      select.setAttribute("aria-label", text("scope"));
      for (const value of ["track", "clip"]) {
        const option = element("option", text(value), select);
        option.value = value;
      }
      select.value = scope;
      select.addEventListener("change", () => {
        scope = select.value;
      });
      element("span", text("offset"), controls);
      const input = element("input", "", controls);
      input.type = "number";
      input.step = ".001";
      input.value = ((review.offsets[pick.clip.id] ?? 0) / review.project.rate).toFixed(3);
      input.setAttribute("aria-label", text("offset"));
      input.addEventListener(
        "change",
        () =>
          void perform(() =>
            move(
              Math.round(Number(input.value) * review.project.rate) -
                (review.offsets[pick.clip.id] ?? 0),
            ),
          ),
      );
      button("left", () => move(-Math.round(review.project.rate / 100)), controls);
      button("right", () => move(Math.round(review.project.rate / 100)), controls);
    }
    button("audition", () => listen(false), controls);
    button("original", () => listen(true), controls);
    button(
      "reset",
      async () => {
        review = await request("/reset", { id: review.id });
      },
      controls,
    );
  }
  async function measure() {
    const result = await request("/measure", { id: review.id, method });
    job = result.jobs[0];
    timer = setTimeout(poll, 500);
  }
  async function poll() {
    if (!review || !job) return;
    try {
      const response = await api.getJobs();
      const item = response.jobs.find((value) => value.id === job);
      if (item && ["completed", "failed", "cancelled"].includes(item.state)) {
        if (item.state === "failed")
          reportError(item.error?.text ?? item.message ?? text("failed"));
        review = await request("");
        job = null;
        draw();
      } else {
        timer = setTimeout(poll, 500);
      }
    } catch (error) {
      job = null;
      reportError(error.message);
      draw();
    }
  }
  async function close(accept) {
    if (job) await api.cancelJob(job);
    await request(accept ? "/apply" : "/cancel", { id: review.id });
    cleanup();
    await refresh();
    if (accept) notice(text("applied"), { undo: true });
  }
  function cleanup() {
    errorText = "";
    clearTimeout(timer);
    clearTimeout(playbackTimer);
    playing = false;
    job = null;
    review = null;
    doc.querySelector(".editor")?.removeAttribute("inert");
    root?.remove();
    root = null;
    doc.defaultView.removeEventListener("keydown", keydown, true);
    previousFocus?.focus();
  }
  function keydown(event) {
    if (!review) return;
    event.stopImmediatePropagation();
    const typing = ["INPUT", "SELECT", "TEXTAREA"].includes(event.target?.tagName);
    if (event.target?.closest("button") && ["Enter", " "].includes(event.key)) return;
    if (event.key === "Tab" || (typing && event.key !== "Escape")) return;
    event.preventDefault();
    if (event.key === "Escape") void perform(() => close(false));
    else if (event.code === "Space") void perform(() => (playing ? stop() : listen(false)));
    else if (event.key === "ArrowLeft" || event.key === "ArrowRight")
      void perform(() =>
        move((event.key === "ArrowLeft" ? -1 : 1) * Math.round(review.project.rate / 100)),
      );
  }
  return {
    update(status) {
      const byTrack = new Map(status.map((row) => [row.track, row]));
      for (const header of doc.querySelectorAll(".track-header[data-track]")) {
        header.querySelector(".sync-review-badge")?.remove();
        const row = byTrack.get(header.dataset.track);
        if (!row) continue;
        const badge = element("span", text(row.manual ? "manual_badge" : "aligned_badge"), null);
        badge.className = "sync-review-badge";
        badge.title = text("badge_hint");
        header.querySelector(".th-main")?.append(badge);
      }
    },
    async open() {
      if (review) return;
      previousFocus = doc.activeElement;
      try {
        review =
          (await request("")) ?? (await request("", { tracks: selectedTrackIds(getState()) }));
        frame = Math.min(getState().playhead ?? 0, length() - 1);
        selected =
          review.project.tracks.find(
            (tr) => review.tracks.includes(tr.id) && tr.id !== review.anchor,
          )?.clips[0]?.id ?? null;
        root = element("section", "", doc.body);
        root.className = "sync-review";
        root.tabIndex = -1;
        root.setAttribute("aria-label", text("title"));
        doc.querySelector(".editor")?.setAttribute("inert", "");
        doc.defaultView.addEventListener("keydown", keydown, true);
        draw();
        root.focus();
      } catch (error) {
        reportError(error.message);
      }
    },
  };
}
