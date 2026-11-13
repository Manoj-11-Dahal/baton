import type {
  AgentColor,
  AgentPreset,
  KeyValue,
  McpServerConfig,
  ModelInfo,
  ModelRef,
  ProviderConfig,
  ProviderDraft,
  ProviderKind,
  Settings,
  SettingsPatch,
  SlashCommand,
} from '../shared/types';
import { ALL_SUBAGENT_TOOLS, DEMO_PROVIDER, DEMO_PROVIDER_ID, DEMO_MODEL_ID, SETTINGS_VERSION, defaultSettings } from '../shared/defaults';
import { readJson, writeJsonAtomic } from './store';
import { keyPreview, type SecretCodec } from './secrets';
import { uid } from './util';

export interface StoredProvider extends ProviderConfig {
  /** Encoded API key (see secrets.ts). */
  secret?: string;
}

export interface StoredSettings extends Omit<Settings, 'providers'> {
  providers: StoredProvider[];
}

/** A provider with its key decoded — only ever exists inside the core process. */
export interface ResolvedProvider {
  id: string;
  name: string;
  kind: ProviderKind;
  baseUrl: string;
  headers: KeyValue[];
  apiKey: string;
}

export interface ResolvedModel {
  provider: ResolvedProvider;
  modelId: string;
  info?: ModelInfo;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** Objects merge recursively; arrays, primitives and `null` replace. */
export function deepMerge<T>(target: T, patch: unknown): T {
  if (patch === undefined) return target;
  if (!isPlainObject(target) || !isPlainObject(patch)) return patch as T;
  const out: Record<string, unknown> = { ...target };
  for (const [key, value] of Object.entries(patch)) {
    if (value === undefined) continue;
    out[key] = isPlainObject(value) && isPlainObject(out[key]) ? deepMerge(out[key], value) : value;
  }
  return out as T;
}

const clamp = (n: unknown, min: number, max: number, fallback: number): number => {
  const v = typeof n === 'number' && Number.isFinite(n) ? n : fallback;
  return Math.min(max, Math.max(min, v));
};

function cleanPairs(pairs: unknown): KeyValue[] {
  if (!Array.isArray(pairs)) return [];
  return pairs
    .filter((p): p is KeyValue => isPlainObject(p) && typeof p.key === 'string')
    .map((p) => ({ key: p.key.trim(), value: String(p.value ?? '') }))
    .filter((p) => p.key);
}

function cleanModels(models: unknown): ModelInfo[] {
  if (!Array.isArray(models)) return [];
  const seen = new Set<string>();
  const out: ModelInfo[] = [];
  for (const m of models) {
    if (!isPlainObject(m) || typeof m.id !== 'string') continue;
    const id = m.id.trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const info: ModelInfo = { id };
    if (typeof m.label === 'string' && m.label.trim() && m.label.trim() !== id) info.label = m.label.trim();
    if (typeof m.contextWindow === 'number' && m.contextWindow > 0) info.contextWindow = Math.round(m.contextWindow);
    out.push(info);
  }
  return out;
}

function normalizeProvider(p: Partial<StoredProvider>): StoredProvider {
  const kind: ProviderKind = p.kind === 'anthropic' || p.kind === 'demo' ? p.kind : 'openai';
  const out: StoredProvider = {
    id: String(p.id),
    name: (p.name ?? '').toString().trim() || 'Provider',
    kind,
    preset: typeof p.preset === 'string' ? p.preset : undefined,
    baseUrl: (p.baseUrl ?? '').toString().trim().replace(/\/+$/, ''),
    headers: cleanPairs(p.headers),
    models: cleanModels(p.models),
    enabled: p.enabled !== false,
    hasKey: false,
  };
  if (typeof p.secret === 'string' && p.secret) {
    out.secret = p.secret;
    out.keyPreview = typeof p.keyPreview === 'string' ? p.keyPreview : '••••••';
  }
  out.hasKey = Boolean(out.secret);
  if (out.id === DEMO_PROVIDER_ID) {
    return { ...structuredClone(DEMO_PROVIDER), enabled: out.enabled };
  }
  return out;
}

const AGENT_COLORS: AgentColor[] = ['sky', 'violet', 'amber', 'rose', 'emerald', 'slate', 'cyan', 'orange'];

const slugify = (value: unknown): string =>
  String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);

function modelRef(value: unknown): ModelRef | null {
  if (!isPlainObject(value) || typeof value.providerId !== 'string' || typeof value.modelId !== 'string') return null;
  return value.providerId && value.modelId ? { providerId: value.providerId, modelId: value.modelId } : null;
}

function uniqueById<T extends { id: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter((item) => !seen.has(item.id) && Boolean(seen.add(item.id)));
}

function normalizeAgent(a: Record<string, unknown>): AgentPreset {
  const name = String(a.name ?? '').trim().slice(0, 40) || 'Agent';
  return {
    id: slugify(a.id) || slugify(name) || uid('agent'),
    name,
    description: String(a.description ?? '').trim().slice(0, 400),
    icon: typeof a.icon === 'string' && a.icon ? a.icon : 'bot',
    color: AGENT_COLORS.includes(a.color as AgentColor) ? (a.color as AgentColor) : 'slate',
    systemPrompt: String(a.systemPrompt ?? ''),
    tools: Array.isArray(a.tools) ? ALL_SUBAGENT_TOOLS.filter((t) => (a.tools as unknown[]).includes(t)) : [],
    model: modelRef(a.model),
    maxSteps: typeof a.maxSteps === 'number' && Number.isFinite(a.maxSteps) ? Math.round(clamp(a.maxSteps, 1, 100, 20)) : null,
    enabled: a.enabled !== false,
    ...(a.builtin === true ? { builtin: true } : {}),
  };
}

function normalizeCommand(c: Record<string, unknown>): SlashCommand {
  const name = slugify(c.name) || 'command';
  return {
    id: typeof c.id === 'string' && c.id ? c.id : uid('cmd'),
    name,
    description: String(c.description ?? '').trim().slice(0, 200),
    prompt: String(c.prompt ?? ''),
  };
}

function normalizeMcpServer(m: Record<string, unknown>): McpServerConfig {
  return {
    id: typeof m.id === 'string' && m.id ? m.id : uid('mcp'),
    name: String(m.name ?? '').trim().slice(0, 40) || 'server',
    command: String(m.command ?? '').trim(),
    args: Array.isArray(m.args) ? m.args.map((x) => String(x)).filter((x) => x !== '') : [],
    env: cleanPairs(m.env),
    enabled: m.enabled !== false,
  };
}

function normalize(raw: unknown): StoredSettings {
  const base = defaultSettings() as StoredSettings;
  if (!isPlainObject(raw)) return base;
  const s = deepMerge(base, raw);
  s.version = SETTINGS_VERSION;

  const providers = Array.isArray(s.providers) ? s.providers : [];
  s.providers = providers.filter((p) => isPlainObject(p) && typeof p.id === 'string' && p.id).map(normalizeProvider);
  if (!s.providers.some((p) => p.id === DEMO_PROVIDER_ID)) s.providers.push(structuredClone(DEMO_PROVIDER));

  const list = (value: unknown, fallback: unknown[]): Record<string, unknown>[] => (Array.isArray(value) ? value : fallback).filter(isPlainObject);
  s.agents = uniqueById(list(s.agents, base.agents).map(normalizeAgent));
  s.commands = uniqueById(list(s.commands, base.commands).map(normalizeCommand));
  s.mcpServers = uniqueById(list(s.mcpServers, []).map(normalizeMcpServer));
  if (!isPlainObject(s.general)) s.general = base.general;
  if (s.general.sendKey !== 'mod-enter') s.general.sendKey = 'enter';
  for (const key of ['notifyOnFinish', 'autoTitle', 'confirmDelete'] as const) s.general[key] = s.general[key] !== false;
  if (!['ask', 'auto-edit', 'full-auto'].includes(s.permissions.defaultMode)) s.permissions.defaultMode = 'ask';
  s.permissions.restrictToWorkspace = s.permissions.restrictToWorkspace !== false;
  s.rules.global = typeof s.rules.global === 'string' ? s.rules.global : '';
  s.rules.loadWorkspaceFiles = s.rules.loadWorkspaceFiles !== false;
  for (const key of ['allowCommands', 'denyCommands', 'protectedPaths'] as const) {
    if (!Array.isArray(s.permissions[key])) s.permissions[key] = base.permissions[key];
    s.permissions[key] = s.permissions[key].map((x) => String(x).trim()).filter(Boolean);
  }
  if (!Array.isArray(s.rules.fileNames)) s.rules.fileNames = base.rules.fileNames;
  s.rules.fileNames = s.rules.fileNames.map((x) => String(x).trim()).filter(Boolean);

  const m = s.models;
  m.maxSteps = Math.round(clamp(m.maxSteps, 1, 200, base.models.maxSteps));
  m.maxSubagentSteps = Math.round(clamp(m.maxSubagentSteps, 1, 100, base.models.maxSubagentSteps));
  m.maxParallelSubagents = Math.round(clamp(m.maxParallelSubagents, 1, 8, base.models.maxParallelSubagents));
  m.requestTimeoutSec = Math.round(clamp(m.requestTimeoutSec, 10, 1800, base.models.requestTimeoutSec));
  m.maxRetries = Math.round(clamp(m.maxRetries, 0, 5, base.models.maxRetries));
  m.contextBudget = Math.round(clamp(m.contextBudget, 4_000, 2_000_000, base.models.contextBudget));
  m.temperature = m.temperature === null || m.temperature === undefined ? null : clamp(m.temperature, 0, 2, 1);
  m.maxOutputTokens =
    m.maxOutputTokens === null || m.maxOutputTokens === undefined ? null : Math.round(clamp(m.maxOutputTokens, 16, 1_000_000, 4096));
  s.permissions.commandTimeoutSec = Math.round(clamp(s.permissions.commandTimeoutSec, 5, 3600, base.permissions.commandTimeoutSec));

  const a = s.appearance;
  a.fontScale = clamp(a.fontScale, 0.85, 1.25, 1);
  a.sidebarWidth = Math.round(clamp(a.sidebarWidth, 208, 420, base.appearance.sidebarWidth));
  a.panelWidth = Math.round(clamp(a.panelWidth, 320, 960, base.appearance.panelWidth));
  if (!['dark', 'light', 'system'].includes(a.theme)) a.theme = 'dark';
  if (a.density !== 'compact') a.density = 'comfortable';
  a.showReasoning = a.showReasoning === true;
  if (!/^#[0-9a-f]{6}$/i.test(a.accent)) a.accent = base.appearance.accent;
  return s;
}

export class SettingsStore {
  private data: StoredSettings;
  /** Decoded API keys, by their stored form. Filled by `init()` and `saveProvider()`; never written to disk. */
  private readonly keys = new Map<string, string>();

  constructor(
    private readonly file: string,
    private readonly codec: SecretCodec,
  ) {
    this.data = normalize(readJson<unknown>(file, null));
  }

  /**
   * Decodes the stored API keys (the OS keychain is asynchronous). Must finish before the first
   * model request; `Core.invoke` waits for it. A key that cannot be decoded — keychain locked,
   * or settings copied from another machine — is treated as missing rather than failing start-up.
   */
  async init(): Promise<void> {
    let changed = false;
    for (const provider of this.data.providers) {
      const stored = provider.secret;
      if (!stored || this.keys.has(stored)) continue;
      try {
        const { plain, stale } = await this.codec.decode(stored);
        if (!plain) continue;
        this.keys.set(stored, plain);
        if (stale) {
          const fresh = await this.codec.encode(plain);
          this.keys.set(fresh, plain);
          const current = this.data.providers.find((p) => p.id === provider.id);
          if (current && current.secret === stored && fresh !== stored) {
            current.secret = fresh;
            changed = true;
          }
        }
      } catch (err) {
        console.warn(`[settings] the saved API key for “${provider.name}” could not be read:`, err instanceof Error ? err.message : err);
      }
    }
    if (changed) this.save();
    else this.forgetUnusedKeys();
  }

  /** Keys of providers that were removed or re-keyed must not linger in memory. */
  private forgetUnusedKeys(): void {
    const inUse = new Set(this.data.providers.map((p) => p.secret));
    for (const stored of this.keys.keys()) if (!inUse.has(stored)) this.keys.delete(stored);
  }

  /** Settings as the UI sees them — no secrets. */
  public(): Settings {
    const { providers, ...rest } = this.data;
    return structuredClone({
      ...rest,
      providers: providers.map(({ secret: _secret, ...p }) => ({ ...p, hasKey: Boolean(_secret) })),
    });
  }

  get raw(): StoredSettings {
    return this.data;
  }

  private save(): void {
    this.forgetUnusedKeys();
    writeJsonAtomic(this.file, this.data, true);
  }

  update(patch: SettingsPatch): Settings {
    const { providers } = this.data;
    const merged = deepMerge(this.data, patch as unknown) as StoredSettings;
    merged.providers = providers; // providers are only changed through saveProvider / removeProvider
    this.data = normalize(merged);
    this.save();
    return this.public();
  }

  reset(): Settings {
    const fresh = defaultSettings() as StoredSettings;
    fresh.providers = this.data.providers;
    fresh.models.main = this.data.models.main;
    fresh.models.subagent = this.data.models.subagent;
    fresh.models.title = this.data.models.title;
    this.data = normalize(fresh);
    this.save();
    return this.public();
  }

  /**
   * A shareable copy of the settings. API keys are never included, and because custom
   * headers and MCP environment variables often hold tokens, only their names are exported.
   */
  export(): string {
    const copy = this.public();
    for (const p of copy.providers) p.headers = p.headers.map((h) => ({ key: h.key, value: '' }));
    for (const m of copy.mcpServers) m.env = m.env.map((e) => ({ key: e.key, value: '' }));
    return JSON.stringify(copy, null, 2);
  }

  import(json: string): Settings {
    let parsed: unknown;
    try {
      parsed = JSON.parse(json);
    } catch {
      throw new Error('That file is not valid JSON.');
    }
    if (!isPlainObject(parsed) || !isPlainObject(parsed.models) || !Array.isArray(parsed.providers)) {
      throw new Error('That file does not look like a settings export.');
    }
    const fill = (pairs: KeyValue[], existing: KeyValue[] | undefined): KeyValue[] =>
      pairs.map((pair) => (pair.value ? pair : { key: pair.key, value: existing?.find((e) => e.key === pair.key)?.value ?? '' }));
    const oldProviders = new Map(this.data.providers.map((p) => [p.id, p]));
    const oldServers = new Map(this.data.mcpServers.map((m) => [m.id, m]));
    const next = normalize(parsed);
    next.providers = next.providers.map((p) => {
      const old = oldProviders.get(p.id);
      const { secret: _ignored, keyPreview: _alsoIgnored, ...rest } = p;
      const merged: StoredProvider = { ...rest, headers: fill(p.headers, old?.headers), hasKey: Boolean(old?.secret) };
      if (old?.secret) {
        merged.secret = old.secret;
        merged.keyPreview = old.keyPreview;
      }
      return merged;
    });
    next.mcpServers = next.mcpServers.map((m) => ({ ...m, env: fill(m.env, oldServers.get(m.id)?.env) }));
    this.data = next;
    this.save();
    return this.public();
  }

  /* ───────────────────────────── Providers ───────────────────────────── */

  async saveProvider(draft: ProviderDraft): Promise<Settings> {
    if (!draft.id) throw new Error('Provider id is missing.');
    const newKey = draft.id !== DEMO_PROVIDER_ID && draft.apiKey !== undefined ? draft.apiKey.trim() : undefined;
    const newSecret = newKey ? await this.codec.encode(newKey) : undefined;

    const existing = this.data.providers.find((p) => p.id === draft.id);
    const next = normalizeProvider({ ...draft, secret: existing?.secret, keyPreview: existing?.keyPreview });

    if (next.id !== DEMO_PROVIDER_ID) {
      if (newKey && newSecret) {
        next.secret = newSecret;
        next.keyPreview = keyPreview(newKey);
        this.keys.set(newSecret, newKey);
      } else if (newKey !== undefined) {
        delete next.secret;
        delete next.keyPreview;
      }
      next.hasKey = Boolean(next.secret);
    }

    if (existing) this.data.providers = this.data.providers.map((p) => (p.id === next.id ? next : p));
    else this.data.providers.push(next);

    this.repairModelRefs();

    // First real provider with a model: make it the default instead of the demo.
    const main = this.data.models.main;
    if (next.kind !== 'demo' && next.enabled && next.models.length && (!main || main.providerId === DEMO_PROVIDER_ID)) {
      this.data.models.main = { providerId: next.id, modelId: next.models[0].id };
    }
    this.save();
    return this.public();
  }

  removeProvider(id: string): Settings {
    if (id === DEMO_PROVIDER_ID) throw new Error('The demo provider cannot be removed, but you can disable it.');
    this.data.providers = this.data.providers.filter((p) => p.id !== id);
    this.repairModelRefs();
    this.save();
    return this.public();
  }

  /** Drop references to providers / models that no longer exist. */
  private repairModelRefs(): void {
    const valid = (ref: ModelRef | null): boolean => {
      if (!ref) return true;
      const p = this.data.providers.find((x) => x.id === ref.providerId);
      return Boolean(p && p.models.some((m) => m.id === ref.modelId));
    };
    const m = this.data.models;
    if (!valid(m.main)) {
      const fallback = this.data.providers.find((p) => p.enabled && p.kind !== 'demo' && p.models.length);
      m.main = fallback
        ? { providerId: fallback.id, modelId: fallback.models[0].id }
        : { providerId: DEMO_PROVIDER_ID, modelId: DEMO_MODEL_ID };
    }
    if (!valid(m.subagent)) m.subagent = null;
    if (!valid(m.title)) m.title = null;
    for (const agent of this.data.agents) if (!valid(agent.model)) agent.model = null;
  }

  /** The saved key of a provider ('' when it has none). Fails clearly when a key is stored but could not be decoded. */
  private decodeKey(p: StoredProvider | undefined): string {
    if (!p?.secret) return '';
    const key = this.keys.get(p.secret);
    if (key === undefined) {
      throw new Error(`The saved API key for “${p.name}” could not be read from the system keychain. Enter it again in Settings → Providers.`);
    }
    return key;
  }

  /** Resolve a form draft (uses the stored key unless the draft carries a new one). */
  resolveDraft(draft: ProviderDraft): ResolvedProvider {
    const stored = this.data.providers.find((p) => p.id === draft.id);
    const n = normalizeProvider({ ...draft });
    return {
      id: n.id,
      name: n.name,
      kind: n.kind,
      baseUrl: n.baseUrl,
      headers: n.headers,
      apiKey: draft.apiKey !== undefined ? draft.apiKey.trim() : this.decodeKey(stored),
    };
  }

  resolveModel(ref: ModelRef | null | undefined): ResolvedModel {
    const r = ref ?? this.data.models.main;
    if (!r) throw new Error('No model selected. Pick one in the composer or in Settings → Models.');
    const p = this.data.providers.find((x) => x.id === r.providerId);
    if (!p) throw new Error('The selected provider no longer exists. Pick another model.');
    if (!p.enabled) throw new Error(`Provider “${p.name}” is disabled. Enable it in Settings → Providers.`);
    if (p.kind !== 'demo' && !p.baseUrl) throw new Error(`Provider “${p.name}” has no base URL. Add one in Settings → Providers.`);
    if (!r.modelId) throw new Error(`No model chosen for provider “${p.name}”.`);
    return {
      provider: { id: p.id, name: p.name, kind: p.kind, baseUrl: p.baseUrl, headers: p.headers, apiKey: this.decodeKey(p) },
      modelId: r.modelId,
      info: p.models.find((m) => m.id === r.modelId),
    };
  }
}
