// Snap state for edge trims and clipboard drops. Keep automation below the usual targets'
// priority: a nearby clip edge or mark wins even when a level change is closer.
// Plain edge trimming was unsnapped; primaryWithoutModifier preserves that behavior.
import { automationTargets } from "./automation-snap.js";
import { moveTargets, snapMove } from "./move-snap.js";

export function createDragSnap(
  project,
  excludedIds,
  marks,
  { primaryWithoutModifier = true } = {},
) {
  const primary = moveTargets(project, excludedIds, marks);
  let automation = null;
  const autoTargets = () => {
    if (automation === null) automation = automationTargets(project, excludedIds);
    return automation;
  };
  let enabled = false;
  let disabled = false;
  return {
    get marks() {
      return enabled && !disabled ? autoTargets() : [];
    },
    update({ mod, alt }) {
      enabled = Boolean(mod);
      disabled = Boolean(alt);
    },
    snap(args) {
      if (disabled || (!enabled && !primaryWithoutModifier)) return { delta: args.delta, at: null };
      const primarySnap = snapMove({ ...args, targets: primary });
      if (primarySnap.at !== null || !enabled) return primarySnap;
      return snapMove({ ...args, targets: autoTargets() });
    },
    end() {
      enabled = false;
      disabled = true;
    },
  };
}
