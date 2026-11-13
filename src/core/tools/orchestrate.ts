import type { AgentPreset } from '../../shared/types';
import { ToolError, str, type ToolDef } from './types';

/**
 * makeOrchestrateTool creates a tool that lets the lead agent decompose work into
 * independent sub-tasks, dispatch them in parallel, and aggregate their results.
 * This is the Codex-style "plan then delegate" pattern.
 */
export function makeOrchestrateTool(agents: AgentPreset[], maxParallel: number): ToolDef {
  const catalogue = agents.map((a) => `- ${a.id}: ${a.description}`).join('\n');
  return {
    name: 'orchestrate',
    description:
      'Break a goal into independent sub-tasks, delegate each to a sub-agent, run them in parallel, and aggregate the results into one report. ' +
      'Use this when the work splits into clearly separable pieces (e.g. review three files, write four doc sections, test five functions). ' +
      `Issue up to ${maxParallel} sub-agents at once.\n` +
      `Sub-agents:\n${catalogue}`,
    parameters: {
      type: 'object',
      properties: {
        goal: { type: 'string', description: 'One-line description of the overall goal.' },
        tasks: {
          type: 'array',
          description: 'Sub-tasks to delegate. Each needs an agent, description, and self-contained prompt.',
          items: {
            type: 'object',
            properties: {
              agent: { type: 'string', enum: agents.map((a) => a.id), description: 'Which sub-agent to use.' },
              description: { type: 'string', description: 'A 3–8 word label shown in the UI.' },
              prompt: { type: 'string', description: 'Complete, self-contained instructions for the sub-agent.' },
            },
            required: ['agent', 'description', 'prompt'],
          },
        },
        aggregate: {
          type: 'string',
          description: 'How to combine the results: "summary" (one paragraph), "list" (bullet per task), or "raw" (concatenate reports).',
          enum: ['summary', 'list', 'raw'],
        },
      },
      required: ['goal', 'tasks', 'aggregate'],
    },
    category: 'meta',
    parallel: false,
    source: 'builtin',
    async run(args, ctx) {
      const goal = str(args, 'goal').trim();
      if (!goal) throw new ToolError('`goal` must not be empty.');
      const tasks = args.tasks;
      if (!Array.isArray(tasks) || tasks.length === 0) throw new ToolError('`tasks` must be a non-empty array.');
      if (tasks.length > maxParallel) throw new ToolError(`Too many tasks: max ${maxParallel} at once.`);
      const aggregate = str(args, 'aggregate');

      const results = await Promise.all(
        tasks.map(async (t: any) => {
          const prompt = str(t, 'prompt').trim();
          if (!prompt) throw new ToolError('Each task needs a non-empty `prompt`.');
          const out = await ctx.runSubagent({
            agent: str(t, 'agent') || undefined,
            description: str(t, 'description', false).trim() || prompt.slice(0, 60),
            prompt,
          });
          return { description: str(t, 'description', false).trim() || prompt.slice(0, 60), report: String(out.content), isError: Boolean(out.isError) };
        }),
      );

      let combined: string;
      if (aggregate === 'list') {
        combined = results.map((r) => `- ${r.description}: ${r.report}`).join('\n');
      } else if (aggregate === 'raw') {
        combined = results.map((r) => `### ${r.description}\n${r.report}`).join('\n\n');
      } else {
        const done = results.filter((r) => !r.isError).length;
        combined = `Orchestration complete: ${done}/${results.length} sub-tasks succeeded.\n\n` + results.map((r) => `- ${r.description}: ${r.report}`).join('\n');
      }

      return {
        content: combined,
        meta: { goal, tasks: results.length, succeeded: results.filter((r) => !r.isError).length },
      };
    },
  };
}

/**
 * makeHandoffTool creates a tool that passes work from one sub-agent to another,
 * forming a chain. Each handoff carries the prior agent's report as context.
 */
export function makeHandoffTool(agents: AgentPreset[]): ToolDef {
  const catalogue = agents.map((a) => `- ${a.id}: ${a.description}`).join('\n');
  return {
    name: 'handoff',
    description:
      'Pass work from the current sub-agent to another sub-agent, carrying the prior report as context. Use for pipelines like architect → coder → reviewer. ' +
      'The receiving sub-agent cannot see the original conversation, so include everything it needs in the prompt.\n' +
      `Sub-agents:\n${catalogue}`,
    parameters: {
      type: 'object',
      properties: {
        agent: { type: 'string', enum: agents.map((a) => a.id), description: 'Which sub-agent to hand off to.' },
        description: { type: 'string', description: 'A 3–8 word label shown in the UI.' },
        prompt: { type: 'string', description: 'Complete instructions, including the prior agent\'s report as context.' },
      },
      required: ['agent', 'description', 'prompt'],
    },
    category: 'meta',
    parallel: false,
    source: 'builtin',
    async run(args, ctx) {
      const prompt = str(args, 'prompt').trim();
      if (!prompt) throw new ToolError('`prompt` must not be empty.');
      return ctx.runSubagent({
        agent: str(args, 'agent') || undefined,
        description: str(args, 'description', false).trim() || prompt.slice(0, 60),
        prompt,
      });
    },
  };
}
