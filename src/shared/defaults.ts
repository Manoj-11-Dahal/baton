import type { AgentPreset, ProviderConfig, ProviderKind, Settings, SlashCommand } from './types';

export interface ProviderPreset {
  id: string;
  name: string;
  kind: ProviderKind;
  baseUrl: string;
  hint: string;
  keyUrl?: string;
  local?: boolean;
  tint: string;
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  { id: 'openai', name: 'OpenAI', kind: 'openai', baseUrl: 'https://api.openai.com/v1', hint: 'Chat Completions API', keyUrl: 'https://platform.openai.com/api-keys', tint: '#10a37f' },
  { id: 'anthropic', name: 'Anthropic', kind: 'anthropic', baseUrl: 'https://api.anthropic.com', hint: 'Messages API', keyUrl: 'https://console.anthropic.com/settings/keys', tint: '#d97757' },
  { id: 'gemini', name: 'Google Gemini', kind: 'openai', baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai', hint: 'OpenAI-compatible endpoint', keyUrl: 'https://aistudio.google.com/apikey', tint: '#4c8df6' },
  { id: 'openrouter', name: 'OpenRouter', kind: 'openai', baseUrl: 'https://openrouter.ai/api/v1', hint: 'Many models, one key', keyUrl: 'https://openrouter.ai/keys', tint: '#6f6af8' },
  { id: 'groq', name: 'Groq', kind: 'openai', baseUrl: 'https://api.groq.com/openai/v1', hint: 'Fast inference', keyUrl: 'https://console.groq.com/keys', tint: '#f55036' },
  { id: 'deepseek', name: 'DeepSeek', kind: 'openai', baseUrl: 'https://api.deepseek.com/v1', hint: 'OpenAI-compatible', keyUrl: 'https://platform.deepseek.com/api_keys', tint: '#4d6bfe' },
  { id: 'ollama', name: 'Ollama', kind: 'openai', baseUrl: 'http://localhost:11434/v1', hint: 'Local models, no key', local: true, tint: '#9aa0a6' },
  { id: 'lmstudio', name: 'LM Studio', kind: 'openai', baseUrl: 'http://localhost:1234/v1', hint: 'Local models, no key', local: true, tint: '#5b8def' },
  { id: 'custom-openai', name: 'Custom (OpenAI-compatible)', kind: 'openai', baseUrl: '', hint: 'Any /chat/completions endpoint', tint: '#7d8590' },
  { id: 'custom-anthropic', name: 'Custom (Anthropic-compatible)', kind: 'anthropic', baseUrl: '', hint: 'Any /v1/messages endpoint', tint: '#7d8590' },
];

export const DEMO_PROVIDER_ID = 'demo';
export const DEMO_MODEL_ID = 'demo-agent';

export const DEMO_PROVIDER: ProviderConfig = {
  id: DEMO_PROVIDER_ID,
  name: 'Demo (offline)',
  kind: 'demo',
  preset: 'demo',
  baseUrl: '',
  headers: [],
  models: [{ id: DEMO_MODEL_ID, label: 'Demo agent (simulated)', contextWindow: 200_000 }],
  enabled: true,
  hasKey: false,
};

export const READ_TOOLS = ['list_dir', 'read_file', 'glob', 'grep'];
export const EDIT_TOOLS = ['write_file', 'edit_file'];
export const ALL_SUBAGENT_TOOLS = [...READ_TOOLS, ...EDIT_TOOLS, 'run_command', 'fetch_url'];

export const TOOL_LABELS: Record<string, string> = {
  list_dir: 'List directory',
  read_file: 'Read file',
  glob: 'Find files',
  grep: 'Search in files',
  write_file: 'Write file',
  edit_file: 'Edit file',
  run_command: 'Run command',
  fetch_url: 'Fetch URL',
  update_plan: 'Update plan',
  task: 'Delegate to sub-agent',
  ask_user: 'Ask the user',
};

export const DEFAULT_AGENTS: AgentPreset[] = [
  {
    id: 'explorer',
    name: 'Explorer',
    description: 'Fast, read-only codebase exploration. Use it to locate files, trace how a feature works or map a directory. Cannot change anything.',
    icon: 'compass',
    color: 'sky',
    systemPrompt:
      'You are Explorer, a read-only code exploration specialist.\n' +
      '- Search broadly first (glob, grep), then read only the files that matter.\n' +
      '- Run several searches in a single step whenever they are independent.\n' +
      '- Never guess: quote file paths and line numbers for every claim.\n' +
      '- Finish with a compact report: what you found, where it lives (path:line), and open questions.',
    tools: [...READ_TOOLS],
    model: null,
    maxSteps: null,
    enabled: true,
    builtin: true,
  },
  {
    id: 'builder',
    name: 'Builder',
    description: 'Implements one well-scoped change end to end: edits files and runs commands to verify. Give it exact files and acceptance criteria.',
    icon: 'hammer',
    color: 'violet',
    systemPrompt:
      'You are Builder, an implementation specialist.\n' +
      '- Read the relevant code before editing. Match the existing style and conventions.\n' +
      '- Make the smallest change that satisfies the task. Prefer edit_file over rewriting whole files.\n' +
      '- Verify your work (build, tests or a quick run) when a command is available.\n' +
      '- Finish with: files changed, what you verified, and anything the lead agent should double-check.',
    tools: [...ALL_SUBAGENT_TOOLS],
    model: null,
    maxSteps: null,
    enabled: true,
    builtin: true,
  },
  {
    id: 'researcher',
    name: 'Researcher',
    description: 'Reads documentation and web pages by URL and compares them with the local code. Returns a sourced summary.',
    icon: 'telescope',
    color: 'amber',
    systemPrompt:
      'You are Researcher. You gather facts from documentation, web pages and the local project.\n' +
      '- Fetch primary sources by URL; prefer official docs.\n' +
      '- Separate what the sources say from your own inference.\n' +
      '- Finish with a concise brief and list every source (URL or path) you relied on.',
    tools: [...READ_TOOLS, 'fetch_url'],
    model: null,
    maxSteps: null,
    enabled: true,
    builtin: true,
  },
  {
    id: 'reviewer',
    name: 'Reviewer',
    description: 'Reviews code or a diff for bugs, security problems and missed edge cases. Read-only apart from running checks.',
    icon: 'scan',
    color: 'rose',
    systemPrompt:
      'You are Reviewer, a meticulous code reviewer.\n' +
      '- Inspect the actual code (and `git diff` when asked about changes) before judging.\n' +
      '- Report only issues you can point to: path:line, why it is a problem, and a concrete fix.\n' +
      '- Order findings by severity (blocker, major, minor, nit). Say so plainly when you find nothing.',
    tools: [...READ_TOOLS, 'run_command'],
    model: null,
    maxSteps: null,
    enabled: true,
    builtin: true,
  },
  {
    id: 'tester',
    name: 'Tester',
    description: 'Writes and runs tests for a given unit or behaviour, then reports failures with their cause.',
    icon: 'flask',
    color: 'emerald',
    systemPrompt:
      'You are Tester. You write focused tests and run them.\n' +
      '- Discover the existing test framework and conventions first; reuse them.\n' +
      '- Cover the happy path, edge cases and failure modes described in the task.\n' +
      '- Run the tests. Report the exact command, the result, and the root cause of any failure.',
    tools: [...ALL_SUBAGENT_TOOLS],
    model: null,
    maxSteps: null,
    enabled: true,
    builtin: true,
  },
  {
    id: 'general',
    name: 'General',
    description: 'General-purpose helper with the full toolset, for self-contained tasks that fit no specialist.',
    icon: 'bot',
    color: 'slate',
    systemPrompt:
      'You are a general-purpose sub-agent. Complete the task you were given autonomously and report the outcome concisely.',
    tools: [...ALL_SUBAGENT_TOOLS],
    model: null,
    maxSteps: null,
    enabled: true,
    builtin: true,
  },
  /* ────────────────────────────────── Codex-style presets ────────────────────────────────── */

  {
    id: 'architect',
    name: 'Architect',
    description: 'Designs system structure: module boundaries, data models, interfaces and integration points. Read-only.',
    icon: 'layers',
    color: 'violet',
    systemPrompt:
      'You are Architect, a system-design specialist.\n' +
      '- Explore the codebase first (glob + grep), then sketch module boundaries, data models and interfaces.\n' +
      '- Prefer composition over inheritance; keep dependencies acyclic where possible.\n' +
      '- Do not write code unless asked — produce a design document with path:line references to existing code.\n' +
      '- Report: proposed structure, affected files, risks, and open questions.',
    tools: [...READ_TOOLS],
    model: null,
    maxSteps: null,
    enabled: true,
    builtin: true,
  },
  {
    id: 'coder',
    name: 'Coder',
    description: 'Implements a feature end to end: edits files, runs tests, and verifies the change.',
    icon: 'code',
    color: 'sky',
    systemPrompt:
      'You are Coder, an implementation specialist.\n' +
      '- Read the relevant code before editing. Match existing style and conventions.\n' +
      '- Make the smallest change that satisfies the task. Prefer edit_file over rewriting whole files.\n' +
      '- Verify your work (run tests or a build) when a command is available.\n' +
      '- Report: files changed, what you verified, and anything the lead agent should double-check.',
    tools: [...ALL_SUBAGENT_TOOLS],
    model: null,
    maxSteps: null,
    enabled: true,
    builtin: true,
  },
  {
    id: 'documenter',
    name: 'Documenter',
    description: 'Writes READMEs, inline docs, changelogs and AGENTS.md from the actual codebase.',
    icon: 'book',
    color: 'emerald',
    systemPrompt:
      'You are Documenter, a technical-writing specialist.\n' +
      '- Base every claim on the actual code; quote path:line for APIs you describe.\n' +
      '- Write for a new contributor: setup, run commands, module overview, key data flows.\n' +
      '- Keep docs concise and scannable (headings, code blocks, bullet lists).\n' +
      '- Report: files written and any gaps you could not document.',
    tools: [...READ_TOOLS, 'write_file', 'edit_file'],
    model: null,
    maxSteps: null,
    enabled: true,
    builtin: true,
  },
  {
    id: 'commit-writer',
    name: 'Commit Writer',
    description: 'Drafts conventional-commit messages and PR descriptions from staged or reviewed changes.',
    icon: 'git-commit',
    color: 'amber',
    systemPrompt:
      'You are Commit Writer. You turn code changes into clear commit messages and PR descriptions.\n' +
      '- Inspect git diff and staged files before writing.\n' +
      '- Use conventional-commit style (feat/fix/docs/refactor/test/chore) with a short subject and a body that explains why.\n' +
      '- Include a PR description: summary, changes, testing steps, and any breaking changes.\n' +
      '- Report: the commit message and PR description text.',
    tools: [...READ_TOOLS, 'run_command'],
    model: null,
    maxSteps: null,
    enabled: true,
    builtin: true,
  },
];

export const DEFAULT_COMMANDS: SlashCommand[] = [
  {
    id: 'explain',
    name: 'explain',
    description: 'Map the project and explain how it fits together',
    prompt: 'Explore this workspace and explain how it is structured: entry points, main modules, how data flows between them, and how to run and test it.',
  },
  {
    id: 'review',
    name: 'review',
    description: 'Review uncommitted changes',
    prompt: 'Review the uncommitted changes in this workspace. Look for bugs, regressions, security issues and missing tests.',
  },
  {
    id: 'tests',
    name: 'tests',
    description: 'Write and run tests for something',
    prompt: 'Write tests for the following, run them, and fix any failures you introduced: ',
  },
  {
    id: 'init',
    name: 'init',
    description: 'Create an AGENTS.md for this workspace',
    prompt: 'Study this workspace and write an AGENTS.md at its root: project overview, setup and run commands, test commands, code conventions.',
  },
];

export const ACCENTS: { id: string; name: string; value: string }[] = [
  { id: 'iris', name: 'Iris', value: '#8e7dff' },
  { id: 'sky', name: 'Sky', value: '#4aa8ff' },
  { id: 'mint', name: 'Mint', value: '#35c99a' },
  { id: 'amber', name: 'Amber', value: '#f0a63a' },
  { id: 'coral', name: 'Coral', value: '#f2725c' },
  { id: 'rose', name: 'Rose', value: '#ec6aa0' },
];

export const SETTINGS_VERSION = 1;

export function defaultSettings(): Settings {
  return {
    version: SETTINGS_VERSION,
    general: {
      defaultWorkspaceId: null,
      theme: 'dark',
      accent: ACCENTS[0].value,
      concurrencyLimit: 3,
      logLevel: 'info',
      dataStorageLocation: '',
      sendKey: 'enter',
      notifyOnFinish: true,
      autoTitle: true,
      confirmDelete: true,
    },
    providers: [structuredClone(DEMO_PROVIDER)],
    models: {
      main: { providerId: DEMO_PROVIDER_ID, modelId: DEMO_MODEL_ID },
      subagent: null,
      title: null,
      temperature: null,
      maxOutputTokens: null,
      maxSteps: 40,
      maxSubagentSteps: 20,
      maxParallelSubagents: 3,
      requestTimeoutSec: 180,
      maxRetries: 2,
      contextBudget: 120_000,
    },
    agents: structuredClone(DEFAULT_AGENTS),
    permissions: {
      defaultMode: 'ask',
      restrictToWorkspace: true,
      allowCommands: ['git status', 'git diff', 'git log', 'ls', 'pwd'],
      denyCommands: ['rm -rf /', 'rm -rf ~', 'rm -rf ~/', 'sudo', 'mkfs*', 'shutdown', 'reboot', 'dd if=*', ':(){'],
      protectedPaths: ['.env', '.env.*', '**/.env', '**/.env.*', '.git/**', '**/*.pem', '**/*.key', '**/id_rsa*'],
      commandTimeoutSec: 120,
    },
    rules: {
      global: '',
      loadWorkspaceFiles: true,
      fileNames: ['AGENTS.md'],
    },
    commands: structuredClone(DEFAULT_COMMANDS),
    mcpServers: [],
    appearance: {
      theme: 'dark',
      accent: ACCENTS[0].value,
      density: 'comfortable',
      fontScale: 1,
      showReasoning: false,
      sidebarWidth: 268,
      panelWidth: 440,
    },
  };
}
