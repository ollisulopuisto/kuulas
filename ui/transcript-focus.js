/** Leave a newly focused control alone when a correction field loses focus. */
export function restoreCorrectionFocus(root, input) {
  if (root.ownerDocument.activeElement === input) root.focus({ preventScroll: true });
}

/** A background preview may focus its action only while focus has not moved. */
export function shouldFocusPutBack(root, previous) {
  return root.ownerDocument.activeElement === previous && root.contains(previous);
}
