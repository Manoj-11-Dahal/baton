export function uid(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

export class AbortError extends Error {
  constructor() {
    super('aborted');
    this.name = 'AbortError';
  }
}

export function isAbort(err: unknown): boolean {
  return err instanceof AbortError || (err instanceof Error && err.name === 'AbortError');
}

export class ToolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ToolError';
  }
}

export class DeniedError extends Error {
  constructor(public readonly feedback?: string) {
    super(feedback ? `Denied: ${feedback}` : 'Denied');
    this.name = 'DeniedError';
  }
}

export function clip(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + `… [${text.length - max} characters clipped]`;
}

export function clipMiddle(text: string, keep: number, note: string): string {
  if (text.length <= keep) return text;
  const half = Math.floor(keep / 2);
  return text.slice(0, half) + `\n… [${note}] …\n` + text.slice(-half);
}

export function safeJsonParse<T>(json: unknown): { ok: true; value: T } | { ok: false; error: string } {
  if (typeof json !== 'string') return { ok: false, error: 'not a string' };
  try {
    const value = JSON.parse(json) as T;
    return { ok: true, value };
  } catch (err) {
    return { ok: false, error: errorMessage(err) };
  }
}

export function estimateTokens(text: string): number {
  // Rough heuristic: ~4 characters per token for English text.
  return Math.max(1, Math.ceil(text.length / 4));
}

export function throwIfAborted(signal: AbortSignal): void {
  if (signal.aborted) throw new AbortError();
}

export class Semaphore {
  private readonly limit: number;
  private readonly waiters: Array<{ release: () => void }> = [];
  private inUse = 0;

  constructor(limit: number) {
    this.limit = limit;
  }

  acquire(signal: AbortSignal): Promise<() => void> {
    if (this.inUse < this.limit) {
      this.inUse += 1;
      return Promise.resolve(() => {
        this.inUse -= 1;
        this.drain();
      });
    }
    return new Promise<() => void>((resolve, reject) => {
      if (signal.aborted) return reject(new AbortError());
      const onAbort = () => {
        reject(new AbortError());
        this.waiters.splice(this.waiters.indexOf(entry), 1);
      };
      const entry = { release: () => {
        this.inUse -= 1;
        this.drain();
        resolve(entry.release);
      } };
      signal.addEventListener('abort', onAbort, { once: true });
      this.waiters.push(entry);
    });
  }

  private drain(): void {
    while (this.inUse < this.limit && this.waiters.length) {
      const entry = this.waiters.shift()!;
      this.inUse += 1;
      entry.release();
    }
  }
}
