import { LlmError } from './types';
import type { ChatMessage, LlmResult, ResolvedModel, StreamEvent } from './types';

export async function streamChat(
  _opts: { provider: ResolvedModel['provider']; model: string; system: string; messages: ChatMessage[]; tools?: { name: string; description: string; parameters: unknown }[]; temperature?: number | null; maxOutputTokens?: number | null; timeoutMs?: number; signal?: AbortSignal },
  _onEvent: (ev: StreamEvent) => void,
): Promise<LlmResult> {
  throw new LlmError('No LLM provider implementation is registered.');
}

export async function streamChatWithRetry(
  opts: Parameters<typeof streamChat>[0],
  onEvent: Parameters<typeof streamChat>[1],
  maxRetries: number,
): Promise<LlmResult> {
  let lastErr: unknown;
  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    try {
      return await streamChat(opts, onEvent);
    } catch (err) {
      lastErr = err;
      if (err instanceof LlmError && !err.retryable) throw err;
      if (attempt === maxRetries) throw err;
      await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
    }
  }
  throw lastErr;
}
