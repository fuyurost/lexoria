/**
 * Tiny typed event bus for cross-cutting session signals.
 * The API client cannot import Pinia stores (layering), so it fires events
 * here; the auth store subscribes once at instantiation time.
 */
type Listener = () => void;

const listeners = new Map<string, Set<Listener>>();

export function onSessionEvent(event: 'expired', cb: Listener): () => void {
  let set = listeners.get(event);
  if (!set) {
    set = new Set();
    listeners.set(event, set);
  }
  set.add(cb);
  return () => {
    set.delete(cb);
  };
}

export function emitSessionEvent(event: 'expired'): void {
  listeners.get(event)?.forEach((cb) => cb());
}
