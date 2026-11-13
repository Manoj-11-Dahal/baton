import type { ChatMessage, LlmResult, StreamEvent } from './types';

export class DemoProvider {
  async streamChat(opts: { model: string; system: string; messages: ChatMessage[]; tools?: { name: string; description: string; parameters: unknown }[]; signal?: AbortSignal }, onEvent: (ev: StreamEvent) => void): Promise<LlmResult> {
    const { signal } = opts;
    const throwIfAborted = () => {
      if (signal?.aborted) throw new Error('aborted');
    };
    throwIfAborted();

    onEvent({ type: 'reasoning', delta: 'I will decompose this task into steps and delegate to sub-agents where useful.' });
    await new Promise((r) => setTimeout(r, 400));
    throwIfAborted();

    const text = 'I have reviewed the request and delegated the independent parts to sub-agents. They are now working in parallel.';
    for (const ch of text) {
      onEvent({ type: 'text', delta: ch });
      await new Promise((r) => setTimeout(r, 15));
      throwIfAborted();
    }

    return {
      text,
      reasoning: 'I will decompose this task into steps and delegate to sub-agents where useful.',
      toolCalls: [],
      incomplete: false,
      stopReason: 'stop',
      usage: { input: 100, output: text.length },
    };
  }
}

export const demoProvider = new DemoProvider();
