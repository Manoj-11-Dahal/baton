import type { AgentPreset, PlanStep } from '../../shared/types';
import { ToolError, str, type ToolDef } from './types';

export const updatePlanTool: ToolDef = {
  name: 'update_plan',
  description:
    'Create or update the task plan shown to the user as a checklist. Send the complete list of steps every time. ' +
    'Use it for work with three or more steps; keep exactly one step `in_progress` and mark steps `completed` as soon as they are done.',
  parameters: {
    type: 'object',
    properties: {
      steps: {
        type: 'array',
        description: 'The full, ordered list of steps.',
        items: {
          type: 'object',
          properties: {
            title: { type: 'string', description: 'Short imperative description of the step.' },
            status: { type: 'string', enum: ['pending', 'in_progress', 'completed'] },
          },
          required: ['title', 'status'],
        },
      },
    },
    required: ['steps'],
  },
  category: 'meta',
  parallel: false,
  source: 'builtin',
  async run(args, ctx) {
    if (!Array.isArray(args.steps)) throw new ToolError('`steps` must be an array of { title, status }.');
    const steps: PlanStep[] = [];
    for (const raw of args.steps.slice(0, 40)) {
      const s = (typeof raw === 'string' ? { title: raw, status: 'pending' } : raw) as Record<string, unknown>;
      const title = String(s?.title ?? s?.step ?? s?.content ?? '').trim();
      if (!title) continue;
      steps.push({ title: title.slice(0, 200), status: normalizeStatus(s.status) ?? 'pending' });
    }
    if (!steps.length) throw new ToolError('The plan needs at least one step with a title.');
    ctx.setPlan(steps);
    const done = steps.filter((s) => s.status === 'completed').length;
    return { content: `Plan updated (${done}/${steps.length} completed).`, meta: { entries: steps.length } };
  },
};

function normalizeStatus(s: unknown): PlanStep['status'] | null {
  if (typeof s !== 'string') return null;
  const m: Record<string, PlanStep['status']> = {
    pending: 'pending', todo: 'pending', not_started: 'pending',
    in_progress: 'in_progress', 'in-progress': 'in_progress', active: 'in_progress', doing: 'in_progress',
    completed: 'completed', complete: 'completed', done: 'completed',
  };
  return m[s.toLowerCase()] ?? null;
}

export function makeTaskTool(agents: AgentPreset[], maxParallel: number): ToolDef {
  const catalogue = agents.map((a) => `- ${a.id}: ${a.description}`).join('\n');
  return {
    name: 'task',
    description:
      'Delegate a self-contained piece of work to a sub-agent. The sub-agent starts with a fresh context, works autonomously with its own tools ' +
      'and returns one final report (you do not see its intermediate steps). ' +
      `Issue several task calls in the same step to run them in parallel (up to ${maxParallel} at once).\n` +
      'The sub-agent cannot see this conversation, so the prompt must stand on its own: the goal, relevant paths, constraints, and what to report back.\n' +
      `Sub-agents:\n${catalogue}`,
    parameters: {
      type: 'object',
      properties: {
        agent: { type: 'string', enum: agents.map((a) => a.id), description: 'Which sub-agent to use.' },
        description: { type: 'string', description: 'A 3–8 word label for this task, shown in the UI.' },
        prompt: { type: 'string', description: 'Complete, self-contained instructions for the sub-agent.' },
      },
      required: ['agent', 'description', 'prompt'],
    },
    category: 'meta',
    parallel: true,
    source: 'builtin',
    async run(args, ctx) {
      const prompt = str(args, 'prompt').trim();
      if (!prompt) throw new ToolError('`prompt` must not be empty.');
      return ctx.runSubagent({
        agent: str(args, 'agent', false) || undefined,
        description: str(args, 'description', false).trim() || prompt.slice(0, 60),
        prompt,
      });
    },
  };
}

export const askUserTool: ToolDef = {
  name: 'ask_user',
  description:
    'Ask the user a question and wait for the answer. Use it only when a decision genuinely changes the outcome and you cannot find the answer yourself. ' +
    'Offer 2–4 short options when the choices are known; the user can always type a free-form answer.',
  parameters: {
    type: 'object',
    properties: {
      question: { type: 'string', description: 'The question, phrased so it can be answered briefly.' },
      options: { type: 'array', items: { type: 'string' }, description: 'Optional suggested answers.' },
    },
    required: ['question'],
  },
  category: 'meta',
  parallel: false,
  source: 'builtin',
  async run(args, ctx) {
    const question = str(args, 'question').trim();
    const options = Array.isArray(args.options) ? args.options.map((o) => String(o).trim()).filter(Boolean).slice(0, 6) : [];
    const answer = await ctx.askUser(question, options);
    return { content: `The user answered: ${answer}`, meta: { answer } };
  },
};
