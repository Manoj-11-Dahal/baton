import fs from 'node:fs';
import path from 'node:path';
import { defaultSettings } from '../shared/defaults';
import type { Bootstrap, EnvInfo, Settings } from '../shared/types';
import { SettingsStore } from './settings';
import { ObfuscatingCodec } from './secrets';
import { WorkspaceStore } from './workspaces';
import { ThreadStore } from './threads';
import { AgentRunner } from './agent/runner';

export interface CoreDeps {
  dataDir: string;
  platform: string;
  isElectron: boolean;
  version: string;
  homeDir: string;
  pathSep: string;
  secureStorage: boolean;
  versions: { node: string; electron?: string; chrome?: string };
}

export class Core {
  private settings: SettingsStore;
  private workspaces: WorkspaceStore;
  private threads: ThreadStore;
  private runner: AgentRunner;
  private emit: ((e: any) => void)[] = [];

  constructor(private readonly deps: CoreDeps) {
    const settingsFile = path.join(deps.dataDir, 'settings.json');
    const workspacesFile = path.join(deps.dataDir, 'workspaces.json');
    const codec = new ObfuscatingCodec();
    this.settings = new SettingsStore(settingsFile, codec);
    this.workspaces = new WorkspaceStore(workspacesFile, deps.dataDir);
    this.threads = new ThreadStore();
    this.runner = new AgentRunner({
      settings: this.settings,
      workspaces: this.workspaces,
      threads: this.threads,
      emit: (e) => {
        for (const fn of this.emit) fn(e);
      },
    });
  }

  emitEvent(e: any): void {
    for (const fn of this.emit) fn(e);
  }

  async init(): Promise<void> {
    await this.settings.init();
  }

  /* ──────────────── bootstrap ──────────────── */

  bootstrap(): Bootstrap {
    const env: EnvInfo = {
      platform: this.deps.platform as any,
      isElectron: this.deps.isElectron,
      version: this.deps.version,
      dataDir: this.deps.dataDir,
      homeDir: this.deps.homeDir,
      pathSep: this.deps.pathSep,
      secureStorage: this.deps.secureStorage,
      versions: this.deps.versions,
    };
    return {
      settings: this.settings.public(),
      workspaces: this.workspaces.list(),
      threads: [],
      env,
      mcp: [],
      epoch: '1',
      seq: 0,
    };
  }

  /* ──────────────── settings ──────────────── */

  settingsUpdate(patch: any): Settings {
    return this.settings.update(patch);
  }

  settingsReset(): Settings {
    return this.settings.reset();
  }

  settingsExport(): { json: string } {
    return { json: this.settings.export() };
  }

  settingsImport(json: string): Settings {
    return this.settings.import(json);
  }

  /* ──────────────── providers ──────────────── */

  async providerSave(p: { provider: any }): Promise<Settings> {
    return this.settings.saveProvider(p.provider);
  }

  providerRemove(p: { id: string }): Settings {
    return this.settings.removeProvider(p.id);
  }

  async providerTest(p: { provider: any; modelId?: string }): Promise<any> {
    const provider = this.settings.resolveDraft(p.provider) as any;
    if (provider.kind !== 'demo' && !provider.baseUrl) {
      return { ok: false, latencyMs: 0, message: 'Base URL is required.' };
    }
    const start = Date.now();
    await new Promise((r) => setTimeout(r, 300));
    const latency = Date.now() - start;
    return {
      ok: true,
      latencyMs: latency,
      message: `Connected to ${provider.name}`,
      reply: 'ok',
      modelCount: provider.models.length,
    };
  }

  async providerFetchModels(p: { provider: any }): Promise<{ models: any[] }> {
    const provider = this.settings.resolveDraft(p.provider) as any;
    return { models: provider.models.length ? provider.models : [{ id: 'default', label: 'Default' }] };
  }

  /* ──────────────── workspaces ──────────────── */

  workspaceAdd(p: { path: string; name?: string }): any {
    return this.workspaces.add(p.path, p.name);
  }

  workspaceUpdate(p: { id: string; patch: any }): any {
    return this.workspaces.update(p.id, p.patch);
  }

  workspaceRemove(p: { id: string }): { workspaces: any[] } {
    return { workspaces: this.workspaces.remove(p.id) };
  }

  workspaceInfo(p: { id: string }): any {
    const w = this.workspaces.get(p.id);
    return { exists: fs.existsSync(w.path), gitBranch: null, rulesFiles: [] };
  }

  /* ──────────────── threads ──────────────── */

  threadSend(p: any): { threadId: string } {
    return this.runner.send(p);
  }

  threadStop(p: { id: string }): null {
    this.runner.stop(p.id);
    return null;
  }

  threadRetry(p: { id: string }): null {
    this.runner.retry(p.id);
    return null;
  }

  threadGet(p: { id: string }): any {
    const file = this.threads.load(p.id);
    return {
      meta: file.meta,
      items: file.items,
      plan: file.meta.plan ?? [],
      approvals: [],
      seq: 0,
    };
  }

  threadUpdate(p: { id: string; patch: any }): any {
    this.threads.updateMeta(p.id, p.patch);
    return this.threads.load(p.id).meta;
  }

  threadRemove(): null {
    return null;
  }

  threadContext(p: { workspaceId: string; mode: string }): any {
    return {
      systemPrompt: 'You are the lead agent.',
      tools: [],
      rulesFiles: [],
      agents: (this.settings.raw.agents ?? []).map((a: any) => ({ id: a.id, name: a.name, description: a.description })),
      estimatedTokens: 0,
    };
  }

  /* ──────────────── approvals ──────────────── */

  approvalRespond(p: any): null {
    this.runner.respond(p);
    return null;
  }

  /* ──────────────── lifecycle ──────────────── */

  async shutdown(): Promise<void> {
    await this.runner.shutdown();
  }
}
