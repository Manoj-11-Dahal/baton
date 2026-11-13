/**
 * Secret codec for API keys.
 *
 * The implementation is intentionally minimal so it can be swapped for the OS
 * keychain (via Electron's native APIs / keytar) without touching the rest of
 * the settings layer. `encode` returns a stored form; `decode` returns the
 * plaintext plus a `stale` flag telling the caller the stored form should be
 * re-encoded.
 */
export interface SecretCodec {
  encode(plain: string): Promise<string>;
  decode(stored: string): Promise<{ plain: string | null; stale: boolean }>;
}

/**
 * Fallback in-memory codec used when no OS keychain is available.
 * Keys are obfuscated (base64) but NOT encrypted — suitable for web mode and
 * for machines without a keychain. Protect the data folder.
 */
export class ObfuscatingCodec implements SecretCodec {
  async encode(plain: string): Promise<string> {
    return Buffer.from(plain, 'utf8').toString('base64');
  }
  async decode(stored: string): Promise<{ plain: string | null; stale: boolean }> {
    try {
      return { plain: Buffer.from(stored, 'base64').toString('utf8'), stale: false };
    } catch {
      return { plain: null, stale: false };
    }
  }
}

/** Short preview of a key, shown in the UI instead of the real value. */
export function keyPreview(key: string): string {
  const visible = key.slice(-4);
  return '•'.repeat(Math.max(0, key.length - 4)) + visible;
}
