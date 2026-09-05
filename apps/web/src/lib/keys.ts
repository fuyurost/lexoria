/** Keyboard helpers shared by the app-shell shortcut handling. */

export function isEditable(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}

/** Whether a global shortcut should fire, given the event target. */
export function shouldIntercept(e: KeyboardEvent): boolean {
  return !e.ctrlKey && !e.metaKey && !e.altKey && !isEditable(e.target);
}
