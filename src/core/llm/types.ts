export interface ChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  toolCallId?: string;
  name?: string;
  toolCalls?: { id: string; name: string; arguments: string }[];
  images?: { mime: string; data: string }[];
}

export interface ChatImage {
  mime: string;
  data: string;
}

export interface LlmResult {
  text: string;
  reasoning: string;
  toolCalls: { id: string; name: string; arguments: string }[];
  incomplete: boolean;
  stopReason: 'stop' | 'length' | 'content_filter' | null;
  usage: { input: number; output: number };
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: string;
}

export class LlmError extends Error {
  constructor(message: string, public readonly status?: number, public readonly retryable = false) {
    super(message);
    this.name = 'LlmError';
  }
}

export interface ResolvedProvider {
  id: string;
  name: string;
  kind: string;
  baseUrl: string;
  headers: { key: string; value: string }[];
  apiKey: string;
}

export interface ResolvedModel {
  provider: ResolvedProvider;
  modelId: string;
  info?: { id: string; label?: string; contextWindow?: number };
}

export interface StreamEvent {
  type: 'reasoning' | 'text' | 'tool_call_start' | 'tool_call_delta';
  index?: number;
  id?: string;
  name?: string;
  delta: string;
}
