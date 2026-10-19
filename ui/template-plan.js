/**
 * Normalizes a track name for case-insensitive, trimmed comparison.
 *
 * @param {string} name
 * @returns {string}
 */
function normName(name) {
  return typeof name === "string" ? name.trim().toLowerCase() : "";
}

/**
 * Plans what applying a template to a project adds.
 *
 * A template is `{ tracks: [{ name, kind }], clips: [{ track, media, name, anchor, length }] }`.
 * A project summary is `{ tracks: [{ id, name, kind, clips: [{ media, start, length }] }] }`.
 *
 * @param {object} template
 * @param {object} project
 * @returns {{
 *   addTracks: Array<{ name: string, kind: string }>,
 *   addClips: Array<{ track: string, media: string, name: string, anchor: number, length: number }>,
 *   skippedClips: Array<{ media: string, name: string, reason: "no_track" | "no_media" }>
 * }}
 */
export function planTemplate(template, project) {
  const tmplTracks = Array.isArray(template?.tracks) ? template.tracks : [];
  const tmplClips = Array.isArray(template?.clips) ? template.clips : [];
  const projTracks = Array.isArray(project?.tracks) ? project.tracks : [];

  const projectTrackNames = new Set();
  const existingMediaByTrack = new Map();

  for (let i = 0; i < projTracks.length; i++) {
    const pt = projTracks[i];
    const norm = normName(pt?.name);
    if (norm) {
      projectTrackNames.add(norm);
      const mediaSet = existingMediaByTrack.get(norm) ?? new Set();
      const clips = Array.isArray(pt?.clips) ? pt.clips : [];
      for (let j = 0; j < clips.length; j++) {
        if (clips[j]?.media) {
          mediaSet.add(clips[j].media);
        }
      }
      existingMediaByTrack.set(norm, mediaSet);
    }
  }

  const addTracks = [];
  const addedTrackNames = new Set();
  const templateTrackNames = new Set();

  for (let i = 0; i < tmplTracks.length; i++) {
    const t = tmplTracks[i];
    const norm = normName(t?.name);
    if (norm) {
      templateTrackNames.add(norm);
      if (!projectTrackNames.has(norm) && !addedTrackNames.has(norm)) {
        addedTrackNames.add(norm);
        addTracks.push({ name: t.name, kind: t.kind });
        if (!existingMediaByTrack.has(norm)) {
          existingMediaByTrack.set(norm, new Set());
        }
      }
    }
  }

  const addClips = [];
  const skippedClips = [];

  for (let i = 0; i < tmplClips.length; i++) {
    const c = tmplClips[i];

    // Check media string
    if (typeof c?.media !== "string" || !c.media.trim()) {
      skippedClips.push({
        media: c?.media,
        name: c?.name,
        reason: "no_media",
      });
      continue;
    }

    // Check track name is in template's own tracks
    const normTrack = normName(c?.track);
    if (!normTrack || !templateTrackNames.has(normTrack)) {
      skippedClips.push({
        media: c.media,
        name: c?.name,
        reason: "no_track",
      });
      continue;
    }

    // Track exists or is being added: check if clip with same media already exists on track
    const trackMedia = existingMediaByTrack.get(normTrack);
    if (trackMedia) {
      if (!trackMedia.has(c.media)) {
        trackMedia.add(c.media);
        addClips.push({
          track: c.track,
          media: c.media,
          name: c.name,
          anchor: c.anchor,
          length: c.length,
        });
      }
    }
  }

  return { addTracks, addClips, skippedClips };
}

/**
 * Returns summary counts for a template plan.
 *
 * @param {object} plan
 * @returns {{ tracks: number, clips: number, skipped: number }}
 */
export function describePlan(plan) {
  return {
    tracks: Array.isArray(plan?.addTracks) ? plan.addTracks.length : 0,
    clips: Array.isArray(plan?.addClips) ? plan.addClips.length : 0,
    skipped: Array.isArray(plan?.skippedClips) ? plan.skippedClips.length : 0,
  };
}
