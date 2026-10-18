/**
 * Pure logic and state transformations for FX layer stacks.
 */

export function addLayer(stack, layer, index = stack.length) {
  if (stack.some((l) => l.id === layer.id)) {
    throw new Error(`Duplicate layer id: ${layer.id}`);
  }
  const idx = Math.max(0, Math.min(stack.length, index));
  return [...stack.slice(0, idx), layer, ...stack.slice(idx)];
}

export function removeLayer(stack, id) {
  const idx = stack.findIndex((l) => l.id === id);
  if (idx === -1) {
    throw new Error(`Unknown layer id: ${id}`);
  }
  return [...stack.slice(0, idx), ...stack.slice(idx + 1)];
}

export function moveLayer(stack, id, delta) {
  const idx = stack.findIndex((l) => l.id === id);
  if (idx === -1) {
    throw new Error(`Unknown layer id: ${id}`);
  }
  const target = Math.max(0, Math.min(stack.length - 1, idx + delta));
  if (target === idx) {
    return [...stack];
  }
  const item = stack[idx];
  const without = [...stack.slice(0, idx), ...stack.slice(idx + 1)];
  return [...without.slice(0, target), item, ...without.slice(target)];
}

export function toggleBypass(stack, id) {
  const idx = stack.findIndex((l) => l.id === id);
  if (idx === -1) {
    throw new Error(`Unknown layer id: ${id}`);
  }
  const item = { ...stack[idx], bypass: !stack[idx].bypass };
  return [...stack.slice(0, idx), item, ...stack.slice(idx + 1)];
}

export function effectiveStatus(layer) {
  if (!layer) return "unknown";
  if (layer.bypass) return "bypassed";
  return layer.status || "unknown";
}

export function activeLayers(stack) {
  if (!stack) return [];
  return stack.filter((l) => !l.bypass);
}

export function describeTier(tier) {
  switch (tier) {
    case 1:
      return "real-time";
    case 2:
      return "analyse once";
    case 3:
      return "render";
    default:
      return "unknown";
  }
}
