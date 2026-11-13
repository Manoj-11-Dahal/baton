export function leadSystemPrompt(o: any): string {
  return `You are ${o.settings?.appName ?? 'Agi Super Harness'}, the lead agent. Plan the work, use tools, delegate to sub-agents, and report back.`;
}

export function subagentSystemPrompt(o: any): string {
  return `You are ${o.preset.name}, a sub-agent of ${o.settings?.appName ?? 'Agi Super Harness'}. Complete the task you were given autonomously and report the outcome concisely.`;
}
