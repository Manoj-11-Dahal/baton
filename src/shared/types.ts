/**
 * Agi Super Harness — shared data model.
 * Types shared by the core (Node side) and the renderer (UI side).
 * Nothing in this file may import Node- or DOM-specific modules.
 */

/* ────────────────────────────── Providers & models ───────────────────────────── */

export type ProviderKind = 'openai' | 'anthropic' | 'demo';

export interface ModelInfo {
  id: string;
  label?: string;
  contextWindow?: number;
}

export interface KeyValue {
  key: string;
  value: string;
}

export interface ProviderConfig {
  id: string;
  name: string;
  kind: ProviderKind;
  preset?: string;
  baseUrl: string;
  headers: KeyValue[];
  models: ModelInfo[];
  enabled: boolean;
  /** API keys never leave the core process; the UI only learns whether one is set. */
  hasKey: boolean;
  keyPreview?: string;
}

export interface ProviderDraft extends Omit<ProviderConfig, 'hasKey' | 'keyPreview'> {
  /** `undefined` keeps the stored key, an empty string clears it. */
  apiKey?: string;
}

export interface ModelRef {
  providerId: string;
  modelId: string;
}

export interface ProviderTestResult {
  ok: boolean;
  latencyMs: number;
  message: string;
  reply?: string;
  modelCount?: number;
}

/* ─────────────────────────────────── Settings ────────────────────────────────── */

export type ThreadMode = 'agent' | 'plan' | 'chat';
export type ApprovalMode = 'ask' | 'auto-edit' | 'full-auto';
export type ToolCategory = 'read' | 'edit' | 'command' | 'network' | 'meta' | 'mcp';
export type AgentColor =
  | 'sky'
  | 'violet'
  | 'amber'
  | 'rose'
  | 'emerald'
  | 'slate'
  | 'cyan'
  | 'orange';

export interface AgentPreset {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: AgentColor;
  systemPrompt: string;
  tools: string[];
  model: ModelRef | null;
  maxSteps: number | null;
  enabled: boolean;
  builtin?: boolean;
}

export interface SlashCommand {
  id: string;
  name: string;
  description: string;
  prompt: string;
}

export interface McpServerConfig {
  id: string;
  name: string;
  command: string;
  args: string[];
  env: KeyValue[];
  enabled: boolean;
}

export interface Settings {
  version: number;
  general: {
    defaultWorkspaceId: string | null;
    theme: 'dark' | 'light' | 'system';
    accent: string;
    concurrencyLimit: number;
    logLevel: 'debug' | 'info' | 'warn' | 'error';
    dataStorageLocation: string;
    sendKey: 'enter' | 'mod-enter';
    notifyOnFinish: boolean;
    autoTitle: boolean;
    confirmDelete: boolean;
  };
  providers: ProviderConfig[];
  models: {
    main: ModelRef | null;
    subagent: ModelRef | null;
    title: ModelRef | null;
    temperature: number | null;
    maxOutputTokens: number | null;
    maxSteps: number;
    maxSubagentSteps: number;
    maxParallelSubagents: number;
    requestTimeoutSec: number;
    maxRetries: number;
    contextBudget: number;
  };
  agents: AgentPreset[];
  permissions: {
    defaultMode: ApprovalMode;
    restrictToWorkspace: boolean;
    allowCommands: string[];
    denyCommands: string[];
    protectedPaths: string[];
    commandTimeoutSec: number;
  };
  rules: {
    global: string;
    loadWorkspaceFiles: boolean;
    fileNames: string[];
  };
  commands: SlashCommand[];
  mcpServers: McpServerConfig[];
  appearance: {
    theme: 'dark' | 'light' | 'system';
    accent: string;
    density: 'comfortable' | 'compact';
    fontScale: number;
    showReasoning: boolean;
    sidebarWidth: number;
    panelWidth: number;
  };
}

export type DeepPartial<T> = T extends (infer U)[]
  ? U[]
  : T extends object
    ? { [K in keyof T]?: DeepPartial<T[K]> }
    : T;

export type SettingsPatch = DeepPartial<Omit<Settings, 'providers' | 'version'>>;

/* ───────────────────────────── Workspaces & threads ──────────────────────────── */

export interface Workspace {
  id: string;
  name: string;
  path: string;
  createdAt: number;
  lastOpenedAt: number;
  collapsed?: boolean;
  isScratch?: boolean;
}

export interface WorkspaceInfo {
  exists: boolean;
  gitBranch: string | null;
  rulesFiles: string[];
}

export type ThreadStatus = 'idle' | 'running' | 'awaiting' | 'error';
export type SubAgentStatus = 'queued' | 'running' | 'done' | 'error';

export interface Usage {
  input: number;
  output: number;
  requests: number;
  contextTokens: number;
}

export interface ThreadMeta {
  id: string;
  workspaceId: string;
  title: string;
  titleSource: 'placeholder' | 'auto' | 'user';
  createdAt: number;
  updatedAt: number;
  status: ThreadStatus;
  mode: ThreadMode;
  approval: ApprovalMode;
  model: ModelRef | null;
  unread: boolean;
  pinned: boolean;
  usage: Usage;
  changedFiles: number;
}

export interface Attachment {
  id: string;
  kind: 'image' | 'text';
  name: string;
  mime: string;
  size: number;
  dataUrl?: string;
  text?: string;
}

interface BaseItem {
  id: string;
  parentId?: string;
  createdAt: number;
}

export interface UserItem extends BaseItem {
  type: 'user';
  text: string;
  attachments?: Attachment[];
}

export interface AssistantItem extends BaseItem {
  type: 'assistant';
  text: string;
  reasoning: string;
  status: 'streaming' | 'done';
  model?: string;
  reasoningMs?: number;
}

export type ToolStatus =
  | 'pending'
  | 'queued'
  | 'awaiting'
  | 'running'
  | 'done'
  | 'error'
  | 'denied'
  | 'cancelled';

export interface ToolMeta {
  path?: string;
  lines?: number;
  additions?: number;
  deletions?: number;
  patch?: string;
  created?: boolean;
  truncated?: boolean;
  matches?: number;
  files?: number;
  entries?: number;
  exitCode?: number | null;
  timedOut?: boolean;
  status?: number;
  bytes?: number;
  title?: string;
  agentId?: string;
  agentName?: string;
  agentIcon?: string;
  agentColor?: AgentColor;
  steps?: number;
  toolCalls?: number;
  tokens?: number;
  model?: string;
  answer?: string;
}

export interface ToolItem extends BaseItem {
  type: 'tool';
  callId: string;
  name: string;
  argsText: string;
  args?: Record<string, unknown>;
  status: ToolStatus;
  output?: string;
  error?: string;
  meta?: ToolMeta;
  startedAt?: number;
  endedAt?: number;
}

export interface NoticeItem extends BaseItem {
  type: 'notice';
  level: 'info' | 'warn' | 'error';
  code: 'aborted' | 'error' | 'max_steps' | 'length' | 'interrupted' | 'info';
  text: string;
}

export type ThreadItem = UserItem | AssistantItem | ToolItem | NoticeItem;

export interface PlanStep {
  title: string;
  status: 'pending' | 'in_progress' | 'completed';
}

export interface ApprovalRequest {
  id: string;
  threadId: string;
  itemId: string;
  kind: 'approval' | 'question';
  category: ToolCategory;
  tool: string;
  title: string;
  detail?: string;
  command?: string;
  patch?: string;
  path?: string;
  url?: string;
  reason?: string;
  agentName?: string;
  agentColor?: AgentColor;
  question?: string;
  options?: string[];
  createdAt: number;
}

export interface ApprovalDecision {
  requestId: string;
  decision: 'allow' | 'allow_thread' | 'deny';
  feedback?: string;
  answer?: string;
}

export interface ThreadData {
  meta: ThreadMeta;
  items: ThreadItem[];
  plan: PlanStep[];
  approvals: ApprovalRequest[];
  seq: number;
}

export interface FileChange {
  path: string;
  status: 'added' | 'modified' | 'deleted';
  additions: number;
  deletions: number;
}

export interface SendParams {
  threadId?: string;
  workspaceId: string;
  text: string;
  attachments?: Attachment[];
  model: ModelRef | null;
  mode: ThreadMode;
  approval: ApprovalMode;
}

/* ──────────────────────────────── File system ────────────────────────────────── */

export interface FsEntry {
  name: string;
  path: string;
  dir: boolean;
  size?: number;
  ignored?: boolean;
}

export interface FsFile {
  path: string;
  size: number;
  binary: boolean;
  truncated: boolean;
  content: string;
  dataUrl?: string;
}

export interface BrowseResult {
  path: string;
  parent: string | null;
  home: string;
  dirs: { name: string; path: string }[];
}

/* ─────────────────────────────────── Context ─────────────────────────────────── */

export interface ToolSummary {
  name: string;
  category: ToolCategory;
  description: string;
  source: 'builtin' | 'mcp';
}

export interface ContextInfo {
  systemPrompt: string;
  tools: ToolSummary[];
  rulesFiles: { name: string; chars: number }[];
  agents: { id: string; name: string; description: string }[];
  estimatedTokens: number;
}

export interface McpServerStatus {
  id: string;
  state: 'stopped' | 'starting' | 'ready' | 'error';
  tools: { name: string; description: string }[];
  error?: string;
}

/* ──────────────────────────────────── Events ─────────────────────────────────── */

export interface ItemPatch {
  status?: AssistantItem['status'] | ToolStatus;
  text?: string;
  reasoning?: string;
  reasoningMs?: number;
  argsText?: string;
  args?: Record<string, unknown>;
  output?: string;
  error?: string;
  meta?: ToolMeta;
  startedAt?: number;
  endedAt?: number;
}

export type AgentEvent =
  | { type: 'thread.created'; thread: ThreadMeta }
  | { type: 'thread.updated'; thread: ThreadMeta }
  | { type: 'thread.removed'; threadId: string }
  | { type: 'threads.reset'; threads: ThreadMeta[] }
  | { type: 'item.added'; threadId: string; item: ThreadItem }
  | { type: 'item.updated'; threadId: string; itemId: string; patch: ItemPatch }
  | { type: 'item.delta'; threadId: string; itemId: string; field: 'text' | 'reasoning' | 'argsText' | 'output'; delta: string }
  | { type: 'items.reset'; threadId: string; items: ThreadItem[] }
  | { type: 'plan.updated'; threadId: string; plan: PlanStep[] }
  | { type: 'approval.requested'; request: ApprovalRequest }
  | { type: 'approval.resolved'; threadId: string; requestId: string }
  | { type: 'run.finished'; threadId: string; status: 'completed' | 'aborted' | 'error'; error?: string }
  | { type: 'changes.updated'; threadId: string }
  | { type: 'settings.updated'; settings: Settings }
  | { type: 'workspaces.updated'; workspaces: Workspace[] }
  | { type: 'mcp.status'; servers: McpServerStatus[] }
  | { type: 'window.state'; maximized: boolean; fullscreen: boolean };

/* ───────────────────────────────────── API ───────────────────────────────────── */

export interface EnvInfo {
  platform: 'darwin' | 'win32' | 'linux' | string;
  isElectron: boolean;
  version: string;
  dataDir: string;
  homeDir: string;
  pathSep: string;
  secureStorage: boolean;
  versions: { node: string; electron?: string; chrome?: string };
}

export interface Bootstrap {
  settings: Settings;
  workspaces: Workspace[];
  threads: ThreadMeta[];
  env: EnvInfo;
  mcp: McpServerStatus[];
  epoch: string;
  seq: number;
}

export interface ApiMethods {
  'app.bootstrap': (p?: undefined) => Bootstrap;

  'settings.update': (p: { patch: SettingsPatch }) => Settings;
  'settings.reset': (p?: undefined) => Settings;
  'settings.export': (p?: undefined) => { json: string };
  'settings.import': (p: { json: string }) => Settings;

  'provider.save': (p: { provider: ProviderDraft }) => Settings;
  'provider.remove': (p: { id: string }) => Settings;
  'provider.test': (p: { provider: ProviderDraft; modelId?: string }) => ProviderTestResult;
  'provider.fetchModels': (p: { provider: ProviderDraft }) => { models: ModelInfo[] };

  'workspace.add': (p: { path: string; name?: string }) => Workspace;
  'workspace.update': (p: { id: string; patch: Partial<Pick<Workspace, 'name' | 'collapsed'>> }) => Workspace;
  'workspace.remove': (p: { id: string }) => { workspaces: Workspace[] };
  'workspace.info': (p: { id: string }) => WorkspaceInfo;

  'fs.tree': (p: { workspaceId: string; path: string }) => { entries: FsEntry[] };
  'fs.read': (p: { workspaceId: string; path: string }) => FsFile;
  'fs.search': (p: { workspaceId: string; query: string; limit?: number }) => { files: string[] };
  'fs.browse': (p: { path?: string }) => BrowseResult;
  'fs.mkdir': (p: { parent: string; name: string }) => { path: string };

  'thread.get': (p: { id: string }) => ThreadData;
  'thread.send': (p: SendParams) => { threadId: string };
  'thread.stop': (p: { id: string }) => null;
  'thread.retry': (p: { id: string }) => null;
  'thread.update': (p: {
    id: string;
    patch: Partial<Pick<ThreadMeta, 'title' | 'pinned' | 'unread' | 'mode' | 'approval' | 'model'>>;
  }) => ThreadMeta;
  'thread.remove': (p: { id: string }) => null;
  'thread.clearAll': (p?: undefined) => null;
  'thread.context': (p: { workspaceId: string; mode: ThreadMode }) => ContextInfo;
  'thread.export': (p: { id: string }) => { markdown: string };

  'approval.respond': (p: ApprovalDecision) => null;

  'changes.list': (p: { threadId: string }) => { changes: FileChange[] };
  'changes.diff': (p: { threadId: string; path: string }) => { patch: string };
  'changes.revert': (p: { threadId: string; path?: string }) => { changes: FileChange[] };

  'mcp.restart': (p?: undefined) => McpServerStatus[];

  'native.pickFolder': (p?: undefined) => { path: string | null };
  'native.reveal': (p: { path: string }) => null;
  'native.openExternal': (p: { url: string }) => null;
  'native.window': (p: { action: 'minimize' | 'maximize' | 'close' | 'state' }) => { maximized: boolean };
}

export type ApiMethod = keyof ApiMethods;
export type ApiParams<M extends ApiMethod> = Parameters<ApiMethods[M]>[0];
export type ApiResult<M extends ApiMethod> = ReturnType<ApiMethods[M]>;
