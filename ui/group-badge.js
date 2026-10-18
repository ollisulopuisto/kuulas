/**
 * Logic and helpers for timeline clip groups.
 */

export function groupMembers(clips, groupId) {
  if (!groupId || !clips || clips.length === 0) {
    return [];
  }
  return clips.filter((c) => c?.group === groupId).map((c) => c.id);
}

export function groupColourIndex(groupId, palette = 6) {
  if (!groupId) {
    return -1;
  }
  const str = String(groupId);
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash * 31 + str.charCodeAt(i)) | 0;
  }
  return ((hash % palette) + palette) % palette;
}

export function groupSpan(clips, groupId) {
  if (!groupId || !clips || clips.length === 0) {
    return null;
  }
  const members = clips.filter((c) => c?.group === groupId);
  if (members.length === 0) {
    return null;
  }
  let minStart = Number.POSITIVE_INFINITY;
  let maxEnd = Number.NEGATIVE_INFINITY;
  for (const m of members) {
    const start = m.start ?? 0;
    const end = m.length !== undefined ? start + m.length : (m.end ?? start);
    if (start < minStart) minStart = start;
    if (end > maxEnd) maxEnd = end;
  }
  return { start: minStart, end: maxEnd };
}

export function groupsOf(clips) {
  const map = new Map();
  if (!clips || clips.length === 0) {
    return map;
  }
  for (const c of clips) {
    if (c?.group) {
      let list = map.get(c.group);
      if (!list) {
        list = [];
        map.set(c.group, list);
      }
      list.push(c.id);
    }
  }
  return map;
}
