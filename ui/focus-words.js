/**
 * Logic for dimming and hiding transcript words based on track focus.
 */

export function wordState(word, focusIds, hide = false) {
  if (!focusIds || focusIds.length === 0) {
    return "normal";
  }
  const focusSet = focusIds instanceof Set ? focusIds : new Set(focusIds);
  if (word && focusSet.has(word.track)) {
    return "normal";
  }
  return hide ? "hidden" : "dim";
}

export function stateRuns(words, focusIds, hide = false) {
  if (!words || words.length === 0) {
    return [];
  }
  const focusSet =
    focusIds && focusIds.length > 0
      ? focusIds instanceof Set
        ? focusIds
        : new Set(focusIds)
      : null;

  const runs = [];
  let currentRun = null;

  for (let i = 0; i < words.length; i++) {
    const state = wordState(words[i], focusSet, hide);
    if (!currentRun || currentRun.state !== state) {
      if (currentRun) {
        runs.push(currentRun);
      }
      currentRun = { state, first: i, last: i };
    } else {
      currentRun.last = i;
    }
  }

  if (currentRun) {
    runs.push(currentRun);
  }

  return runs;
}

export function visibleCount(words, focusIds, hide = false) {
  if (!words || words.length === 0) {
    return 0;
  }
  if (!hide) {
    return words.length;
  }
  const focusSet =
    focusIds && focusIds.length > 0
      ? focusIds instanceof Set
        ? focusIds
        : new Set(focusIds)
      : null;
  if (!focusSet) {
    return words.length;
  }

  let count = 0;
  for (let i = 0; i < words.length; i++) {
    if (wordState(words[i], focusSet, hide) !== "hidden") {
      count++;
    }
  }
  return count;
}
