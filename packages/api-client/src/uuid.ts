/** RFC 4122 v4 UUID used for idempotency keys (`client_event_id`). */

function fillFallback(bytes: Uint8Array): void {
  for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
}

/** Returns a new UUID v4 string without pulling in a dependency. */
export function newClientEventId(): string {
  const cryptoObj = globalThis.crypto;
  const bytes = new Uint8Array(16);
  try {
    if (cryptoObj && typeof cryptoObj.getRandomValues === 'function') {
      cryptoObj.getRandomValues(bytes);
    } else {
      fillFallback(bytes);
    }
  } catch {
    fillFallback(bytes);
  }
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40; // version 4
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80; // variant 10
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0'));
  return (
    hex.slice(0, 4).join('') +
    '-' +
    hex.slice(4, 6).join('') +
    '-' +
    hex.slice(6, 8).join('') +
    '-' +
    hex.slice(8, 10).join('') +
    '-' +
    hex.slice(10, 16).join('')
  );
}
