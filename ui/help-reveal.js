// Help highlights must reveal real UI state, not just animate an invisible node.
// Panel activation is owned by the app so its tab, focus and sidebar state agree.
export function revealHelpTarget(target, revealPanel = () => {}) {
  const panel = target.closest?.("[data-panel]")?.dataset.panel;
  if (panel) revealPanel(panel);
  for (let node = target.parentElement; node; node = node.parentElement) {
    if (node.tagName === "DETAILS") node.open = true;
  }
}
