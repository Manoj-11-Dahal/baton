import type {
  AgentEvent,
  AgentPreset,
  ApprovalDecision,
  ApprovalRequest,
  SendParams,
} from '../../shared/types';
import type { StoredSettings } from '../settings';
import { Semaphore, uid, errorMessage, isAbort, AbortError } from '../util';
import type { ResolvedModel } from '../settings';

export interface RunnerDeps {
  settings: any; // SettingsStore
  workspaces: any; // WorkspaceStore
  threads: any; // ThreadStore
  emit: (e: AgentEvent) => void;
}

interface ActiveRun {
  controller: AbortController;
  slots: Semaphore;
  done: Promise<void>;
}

interface PendingPrompt {
  request: ApprovalRequest;
  settle: (decision: ApprovalDecision) => void;
}

interface LoopContext {
  file: any;
  workspace: any;
  run: ActiveRun;
  model: ResolvedModel;
  system: string;
  transcript: any[];
  depth: number;
  parentId?: string;
  preset?: AgentPreset;
  maxSteps: number;
  rules: any[];
}

interface LoopResult {
  finalText: string;
  steps: number;
  toolCalls: number;
  tokens: number;
  hitLimit: boolean;
}

function makeTitle(text: string): string {
  const line = text.trim().split('\n')[0].replace(/\s+/g, ' ');
  if (!line) return 'New thread';
  return line.length > 52 ? `${line.slice(0, 52).trimEnd()}…` : line;
}

export class AgentRunner {
  private readonly runs = new Map<string, ActiveRun>();
  private readonly prompts = new Map<string, PendingPrompt>();

  constructor(private readonly deps: RunnerDeps) {}

  isRunning(threadId: string): boolean {
    return this.runs.has(threadId);
  }

  pendingPrompts(threadId: string): ApprovalRequest[] {
    return [...this.prompts.values()].filter((p) => p.request.threadId === threadId).map((p) => p.request);
  }

  send(p: SendParams): { threadId: string } {
    const { threads, workspaces } = this.deps;
    const text = (p.text ?? '').trim();
    if (!text && !p.attachments?.length) throw new Error('Type a message first.');

    let file: any;
    let workspace: any;
    if (p.threadId) {
      file = threads.load(p.threadId);
      if (this.runs.has(file.meta.id)) throw new Error('This thread is still working. Stop it or wait for it to finish.');
      workspace = workspaces.get(file.meta.workspaceId);
    } else {
      workspace = workspaces.get(p.workspaceId);
      file = threads.create({ workspaceId: workspace.id, mode: p.mode, approval: p.approval, model: p.model });
    }
    const threadId = file.meta.id;
    workspaces.touch(workspace.id);

    const meta: any = { mode: p.mode, approval: p.approval, model: p.model, updatedAt: Date.now() };
    const needsTitle = file.meta.titleSource === 'placeholder';
    if (needsTitle) {
      meta.title = makeTitle(text || p.attachments?.[0]?.name || 'New thread');
      meta.titleSource = 'auto';
    }
    threads.updateMeta(threadId, meta);

    threads.addItem(threadId, {
      id: uid('it'),
      type: 'user',
      text,
      attachments: p.attachments?.length ? p.attachments : undefined,
      createdAt: Date.now(),
    });

    this.start(file, workspace);
    if (needsTitle && text) void this.generateTitle(file, text);
    return { threadId };
  }

  stop(threadId: string): void {
    this.runs.get(threadId)?.controller.abort();
  }

  retry(threadId: string): void {
    const { threads, workspaces } = this.deps;
    const file = threads.load(threadId);
    if (this.runs.has(threadId)) throw new Error('This thread is still working.');
    this.start(file, workspaces.get(file.meta.workspaceId));
  }

  respond(decision: ApprovalDecision): void {
    const pending = this.prompts.get(decision.requestId);
    if (!pending) throw new Error('This request is no longer waiting for an answer.');
    pending.settle(decision);
  }

  async shutdown(): Promise<void> {
    const all = [...this.runs.values()];
    for (const run of all) run.controller.abort();
    if (!all.length) return;
    let timer: NodeJS.Timeout | undefined;
    const timeout = new Promise<void>((resolve) => {
      timer = setTimeout(resolve, 2500);
    });
    await Promise.race([Promise.allSettled(all.map((r) => r.done)), timeout]);
    clearTimeout(timer);
  }

  private start(file: any, workspace: any): void {
    const { threads, emit, settings } = this.deps;
    const threadId = file.meta.id;
    const run: ActiveRun = {
      controller: new AbortController(),
      slots: new Semaphore(settings.raw.models.maxParallelSubagents),
      done: Promise.resolve(),
    };
    this.runs.set(threadId, run);

    run.done = (async () => {
      let status: 'completed' | 'aborted' | 'error' = 'completed';
      let error: string | undefined;
      try {
        await this.runLead(file, workspace, run);
      } catch (err) {
        if (run.controller.signal.aborted || isAbort(err)) {
          status = 'aborted' as const;
          this.notice(threadId, 'info', 'aborted', 'Stopped.');
        } else {
          status = 'error';
          error = errorMessage(err) || 'Something went wrong.';
          this.notice(threadId, 'error', 'error', error);
        }
      } finally {
        this.runs.delete(threadId);
        this.closeOpenItems(file);
        if (threads.has(threadId)) {
          threads.updateMeta(threadId, { status: status === 'error' ? 'error' : 'idle', updatedAt: Date.now() });
          threads.saveNow(threadId);
        }
        emit({ type: 'run.finished', threadId, status, error });
      }
    })();
  }

  private notice(threadId: string, level: string, code: string, text: string): void {
    if (!this.deps.threads.has(threadId)) return;
    this.deps.threads.addItem(threadId, { id: uid('it'), type: 'notice', level, code, text, createdAt: Date.now() });
  }

  private closeOpenItems(file: any): void {
    const { threads } = this.deps;
    const threadId = file.meta.id;
    if (!threads.has(threadId)) return;
    const activeStatuses = new Set(['pending', 'queued', 'awaiting', 'running', 'streaming']);
    for (const item of file.items) {
      if (item.type === 'assistant' && item.status === 'streaming') {
        threads.patchItem(threadId, item.id, { status: 'done' });
      } else if (item.type === 'tool' && activeStatuses.has(item.status)) {
        threads.patchItem(threadId, item.id, { status: 'cancelled', endedAt: Date.now() });
      }
    }
  }

  private async runLead(file: any, workspace: any, run: ActiveRun): Promise<void> {
    const settings = this.deps.settings.raw;
    const model = this.deps.settings.resolveModel(file.meta.model);
    await this.loop({
      file,
      workspace,
      run,
      model,
      system: 'You are the lead agent. Plan, delegate to sub-agents, and report back.',
      transcript: file.transcript,
      depth: 0,
      maxSteps: settings.models.maxSteps,
      rules: [],
    });
  }

  private async loop(ctx: LoopContext): Promise<LoopResult> {
    const { threads } = this.deps;
    const { file, run } = ctx;
    const threadId = file.meta.id;
    const signal = run.controller.signal;

    let steps = 0;

    for (;;) {
      if (signal.aborted) throw new AbortError();
      if (steps >= ctx.maxSteps) {
        this.notice(threadId, 'warn', 'max_steps', `Paused after ${ctx.maxSteps} steps.`);
        return { finalText: '', steps, toolCalls: 0, tokens: 0, hitLimit: true };
      }
      steps += 1;

      const assistant = threads.addItem(threadId, {
        id: uid('it'),
        type: 'assistant',
        parentId: ctx.parentId,
        text: 'I am working on your request.',
        reasoning: '',
        status: 'streaming',
        model: ctx.model.modelId,
        createdAt: Date.now(),
      });

      await new Promise((r) => setTimeout(r, 300));
      if (signal.aborted) throw new AbortError();

      threads.patchItem(threadId, assistant.id, { status: 'done' });

      if (ctx.depth === 0) {
        return { finalText: assistant.text, steps, toolCalls: 0, tokens: 0, hitLimit: false };
      }
      return { finalText: assistant.text, steps, toolCalls: 0, tokens: 0, hitLimit: false };
    }
  }

  private async runSubagent(parent: LoopContext, item: any, args: { agent?: string; description: string; prompt: string }): Promise<any> {
    const { threads } = this.deps;
    const { file, run, workspace } = parent;
    const threadId = file.meta.id;
    const settings = this.deps.settings.raw;
    if (parent.depth >= 1) throw new Error('Sub-agents cannot delegate further.');

    const agents = settings.agents?.filter((a: AgentPreset) => a.enabled) ?? [];
    const wanted = (args.agent ?? '').toLowerCase();
    const preset = agents.find((a: AgentPreset) => a.id.toLowerCase() === wanted || a.name.toLowerCase() === wanted)
      ?? agents.find((a: AgentPreset) => a.id === 'general') ?? agents[0];
    if (!preset) throw new Error('No sub-agents are enabled (Settings → Agents).');

    let model: ResolvedModel;
    try {
      model = this.deps.settings.resolveModel(preset.model ?? settings.models.subagent ?? file.meta.model);
    } catch (err) {
      throw new Error(`Sub-agent “${preset.name}” has no usable model: ${errorMessage(err)}`);
    }

    threads.patchItem(threadId, item.id, { status: 'queued', meta: { agentId: preset.id, agentName: preset.name, agentIcon: preset.icon, agentColor: preset.color, model: model.modelId } });

    const release = await run.slots.acquire(run.controller.signal);
    try {
      threads.patchItem(threadId, item.id, { status: 'running', startedAt: Date.now() });
      const result = await this.loop({
        file,
        workspace,
        run,
        model,
        system: `You are ${preset.name}. ${preset.systemPrompt}`,
        transcript: [{ role: 'user', content: args.prompt }],
        depth: parent.depth + 1,
        parentId: item.id,
        preset,
        maxSteps: preset.maxSteps ?? settings.models.maxSubagentSteps,
        rules: parent.rules,
      });
      const report = result.finalText.trim() || '(The sub-agent finished without writing a report.)';
      const meta = { agentId: preset.id, agentName: preset.name, agentIcon: preset.icon, agentColor: preset.color, model: model.modelId, steps: result.steps, toolCalls: result.toolCalls, tokens: result.tokens };
      threads.patchItem(threadId, item.id, { status: 'done', endedAt: Date.now(), output: report, meta });
      return { content: report, output: report, meta };
    } catch (err) {
      if (run.controller.signal.aborted || isAbort(err)) throw new AbortError();
      const message = errorMessage(err);
      this.notice(threadId, 'error', 'error', message);
      threads.patchItem(threadId, item.id, { status: 'error', endedAt: Date.now(), error: message.slice(0, 300) });
      return { content: `The ${preset.name} sub-agent failed: ${message}`, isError: true, meta: { agentId: preset.id, agentName: preset.name } };
    } finally {
      release();
    }
  }

  private async generateTitle(file: any, text: string): Promise<void> {
    // Title generation is a nicety; skipped in the minimal harness.
    return;
  }
}
