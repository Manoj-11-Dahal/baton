export interface ThreadFile {
  meta: any;
  items: any[];
  transcript: any[];
  snapshots: Record<string, { before: string }>;
  grants: string[];
}

export class ThreadStore {
  private threads = new Map<string, ThreadFile>();

  create(opts: { workspaceId: string; mode: string; approval: string; model: any }): ThreadFile {
    const id = `thread_${Date.now().toString(36)}`;
    const now = Date.now();
    const meta = {
      id,
      workspaceId: opts.workspaceId,
      title: 'New thread',
      titleSource: 'placeholder',
      createdAt: now,
      updatedAt: now,
      status: 'idle' as const,
      mode: opts.mode,
      approval: opts.approval,
      model: opts.model,
      unread: false,
      pinned: false,
      usage: { input: 0, output: 0, requests: 0, contextTokens: 0 },
      changedFiles: 0,
    };
    const file: ThreadFile = { meta, items: [], transcript: [], snapshots: {}, grants: [] };
    this.threads.set(id, file);
    return file;
  }

  load(id: string): ThreadFile {
    const f = this.threads.get(id);
    if (!f) throw new Error('Thread not found.');
    return f;
  }

  has(id: string): boolean {
    return this.threads.has(id);
  }

  addItem(threadId: string, item: any): any {
    const f = this.load(threadId);
    f.items.push(item);
    return item;
  }

  patchItem(threadId: string, itemId: string, patch: any): void {
    const f = this.load(threadId);
    const item = f.items.find((i: any) => i.id === itemId);
    if (!item) return;
    Object.assign(item, patch);
  }

  getItem(threadId: string, itemId: string): any | undefined {
    const f = this.load(threadId);
    return f.items.find((i: any) => i.id === itemId);
  }

  updateMeta(threadId: string, patch: any): void {
    const f = this.load(threadId);
    Object.assign(f.meta, patch);
  }

  saveNow(threadId: string): void {
    // Persistence hook; no-op in minimal harness.
  }
}
