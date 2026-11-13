import fs from 'node:fs';
import path from 'node:path';

/**
 * Read a JSON file. A missing file yields the fallback; a corrupt file is moved
 * aside (never silently overwritten) and the fallback is returned.
 */
export function readJson<T>(file: string, fallback: T): T {
  let raw: string;
  try {
    raw = fs.readFileSync(file, 'utf8');
  } catch {
    return fallback;
  }
  try {
    return JSON.parse(raw) as T;
  } catch {
    try {
      fs.renameSync(file, `${file}.corrupt-${Date.now()}`);
    } catch {
      /* ignore */
    }
    return fallback;
  }
}

/** Write via a temp file + rename so a crash never leaves a half-written file. */
export function writeJsonAtomic(file: string, data: unknown, pretty = false): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, pretty ? 2 : undefined), { mode: 0o600 });
  fs.renameSync(tmp, file);
}

/** Coalesces frequent saves (e.g. while a response is streaming). */
export class SaveQueue {
  private timers = new Map<string, NodeJS.Timeout>();
  private jobs = new Map<string, () => void>();

  schedule(key: string, job: () => void, delayMs = 600): void {
    this.jobs.set(key, job);
    if (this.timers.has(key)) return;
    const timer = setTimeout(() => this.flush(key), delayMs);
    timer.unref?.();
    this.timers.set(key, timer);
  }

  flush(key: string): void {
    const timer = this.timers.get(key);
    if (timer) clearTimeout(timer);
    this.timers.delete(key);
    const job = this.jobs.get(key);
    this.jobs.delete(key);
    if (job) {
      try {
        job();
      } catch (err) {
        console.error(`[store] failed to save ${key}:`, err);
      }
    }
  }

  cancel(key: string): void {
    const timer = this.timers.get(key);
    if (timer) clearTimeout(timer);
    this.timers.delete(key);
    this.jobs.delete(key);
  }

  flushAll(): void {
    for (const key of [...this.jobs.keys()]) this.flush(key);
  }
}
