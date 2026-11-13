/** Minimal CSS className utility. */
export function cx(...classes: (string | undefined | null | boolean)[]): string {
  return classes.filter(Boolean).join(' ');
}

export function clamp(n: unknown, min: number, max: number, fallback: number): number {
  const v = typeof n === 'number' && Number.isFinite(n) ? n : fallback;
  return Math.min(max, Math.max(min, v));
}

export function truncate(text: string, len: number): string {
  if (!text) return '';
  return text.length > len ? text.slice(0, len).trimEnd() + '…' : text;
}

export function timeAgo(timestamp: number, now: number): string {
  const secs = Math.floor((now - timestamp) / 1000);
  if (secs < 10) return 'just now';
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function compactNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function tildePath(p: string, home: string): string {
  if (!p) return '';
  if (home && p.startsWith(home)) return '~' + p.slice(home.length);
  return p;
}

export function baseName(p: string): string {
  return p.split('/').pop() ?? p;
}

export function dirName(p: string): string {
  const parts = p.split('/');
  parts.pop();
  return parts.join('/');
}

export function extension(name: string): string {
  const m = /\.([^.]+)$/.exec(name);
  return m ? m[1].toLowerCase() : '';
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

export function plural(n: number, one: string, other?: string): string {
  return n === 1 ? `${n} ${one}` : `${n} ${other ?? one + 's'}`;
}

export function errorText(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

export function copyText(text: string): Promise<boolean> {
  return navigator.clipboard
    .writeText(text)
    .then(() => true)
    .catch(() => false);
}

export function downloadText(filename: string, content: string, mime = 'text/plain'): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function modKey(env: { platform: string }): string {
  return env.platform === 'darwin' ? '⌘' : 'Ctrl';
}
