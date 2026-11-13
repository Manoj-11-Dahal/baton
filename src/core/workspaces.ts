import fs from 'node:fs';
import path from 'node:path';
import type { Workspace } from '../shared/types';
import { readJson, writeJsonAtomic } from './store';
import { uid } from './util';

export class WorkspaceStore {
  private items: Workspace[];

  constructor(private readonly file: string, private readonly dataDir: string) {
    const raw = readJson<unknown>(file, []);
    this.items = Array.isArray(raw) ? (raw.filter((w) => w && typeof w.id === 'string' && typeof w.path === 'string') as Workspace[]) : [];
    this.ensureScratch();
  }

  private save(): void {
    writeJsonAtomic(this.file, this.items, true);
  }

  private ensureScratch(): void {
    const dir = path.join(this.dataDir, 'scratch');
    try {
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(path.join(dir, 'README.md'), '# Scratchpad\n\nThis is Agi Super Harness\'s built-in scratch workspace.');
      }
    } catch {
      /* scratch folder is a convenience, not a requirement */
    }
    if (!this.items.some((w) => w.isScratch)) {
      const now = Date.now();
      this.items.push({ id: 'scratch', name: 'Scratchpad', path: dir, createdAt: now, lastOpenedAt: now, isScratch: true });
      this.save();
    }
  }

  list(): Workspace[] {
    return structuredClone(this.items);
  }

  get(id: string): Workspace {
    const w = this.items.find((x) => x.id === id);
    if (!w) throw new Error('Workspace not found.');
    return w;
  }

  add(dir: string, name?: string): Workspace {
    const resolved = path.resolve(dir.trim());
    let stat: fs.Stats;
    try {
      stat = fs.statSync(resolved);
    } catch {
      throw new Error(`Folder not found: ${resolved}`);
    }
    if (!stat.isDirectory()) throw new Error(`Not a folder: ${resolved}`);
    const existing = this.items.find((w) => path.resolve(w.path) === resolved);
    if (existing) {
      existing.lastOpenedAt = Date.now();
      this.save();
      return structuredClone(existing);
    }
    const now = Date.now();
    const ws: Workspace = {
      id: uid('ws'),
      name: name?.trim() || path.basename(resolved) || resolved,
      path: resolved,
      createdAt: now,
      lastOpenedAt: now,
    };
    this.items.push(ws);
    this.save();
    return structuredClone(ws);
  }

  update(id: string, patch: Partial<Pick<Workspace, 'name' | 'collapsed'>>): Workspace {
    const w = this.get(id);
    if (typeof patch.name === 'string' && patch.name.trim()) w.name = patch.name.trim();
    if (typeof patch.collapsed === 'boolean') w.collapsed = patch.collapsed;
    this.save();
    return structuredClone(w);
  }

  touch(id: string): void {
    const w = this.items.find((x) => x.id === id);
    if (!w) return;
    w.lastOpenedAt = Date.now();
    this.save();
  }

  remove(id: string): Workspace[] {
    const w = this.get(id);
    if (w.isScratch) throw new Error('The scratch workspace cannot be removed.');
    this.items = this.items.filter((x) => x.id !== id);
    this.save();
    return this.list();
  }
}
