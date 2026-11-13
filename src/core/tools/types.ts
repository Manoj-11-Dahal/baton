export interface ToolContext {
  workspaceRoot: string;
  settings: any;
  signal: AbortSignal;
  depth: number;
  update: (patch: any) => void;
  appendOutput: (text: string) => void;
  authorize: (req: any) => Promise<void>;
  snapshot: (abs: string, before: string | null) => void;
  filesChanged: () => void;
  setPlan: (steps: any[]) => void;
  askUser: (question: string, options: string[]) => Promise<string>;
  runSubagent: (a: { agent?: string; description: string; prompt: string }) => Promise<ToolOutput>;
}

export interface ToolOutput {
  content: string;
  isError?: boolean;
  output?: string;
  meta?: any;
}

export interface ToolDef {
  name: string;
  description: string;
  parameters: any;
  category: 'read' | 'edit' | 'command' | 'network' | 'meta' | 'mcp';
  parallel: boolean;
  source: 'builtin' | 'mcp';
  run: (args: Record<string, unknown>, ctx: ToolContext) => Promise<ToolOutput>;
}

export class ToolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ToolError';
  }
}

export class DeniedError extends Error {
  constructor(public readonly feedback?: string) {
    super(feedback ? `Denied: ${feedback}` : 'Denied');
    this.name = 'DeniedError';
  }
}

export function str(args: Record<string, unknown>, key: string, required = true): string {
  const v = args[key];
  if (v === undefined || v === null) {
    if (required) throw new ToolError(`\`${key}\` must not be empty.`);
    return '';
  }
  return String(v);
}
