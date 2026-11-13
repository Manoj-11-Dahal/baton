import { useState } from 'react';
import { Icon } from '../icons';
import { cx } from '../lib/format';
import { call } from '../api';
import { errorText, toast } from '../store';

interface RefactorRequest {
  path: string;
  content: string;
}

export function RefactorPanel() {
  const [path, setPath] = useState('');
  const [content, setContent] = useState('');
  const [instruction, setInstruction] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const runRefactor = async (): Promise<void> => {
    if (!path.trim() || !instruction.trim()) return toast('error', 'Enter a file path and instruction.');
    setRunning(true);
    setResult(null);
    try {
      // 1. Coder sub-agent produces a proposed edit
      const proposal = await call('thread.send', {
        text: `You are a Coder sub-agent. Refactor the file at ${path} according to this instruction: ${instruction}\n\nCurrent file content:\n\`\`\`\n${content}\n\`\`\`\nReturn only the updated file content, no explanation.`,
        workspaceId: 'scratch',
        model: null,
        mode: 'agent',
        approval: 'ask',
      });
      const threadId = (proposal as any).threadId;

      // 2. Reviewer sub-agent reviews the proposed change
      const review = await call('thread.send', {
        text: `You are a Reviewer sub-agent. Review this proposed change to ${path} for bugs, regressions, and style issues. Proposed content:\n\`\`\`\n${content}\n\`\`\`\nReport issues with path:line references, or say "looks good".`,
        workspaceId: 'scratch',
        model: null,
        mode: 'agent',
        approval: 'ask',
      });

      setResult(`Refactor proposed by Coder (thread ${threadId}). Reviewer review (thread ${(review as any).threadId}). Apply the change below when approved.`);
      toast('success', 'Refactor proposed and reviewed.');
    } catch (err: any) {
      toast('error', errorText(err));
    } finally {
      setRunning(false);
    }
  };

  const applyChange = async (): Promise<void> => {
    if (!result || !path.trim()) return;
    setRunning(true);
    try {
      await call('thread.send', {
        text: `Apply the following change to ${path}:\n\`\`\`\n${content}\n\`\`\``,
        workspaceId: 'scratch',
        model: null,
        mode: 'agent',
        approval: 'ask',
      });
      toast('success', `Change applied to ${path}.`);
      setResult(null);
    } catch (err: any) {
      toast('error', errorText(err));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="refactor-panel">
      <header className="refactor-header">
        <Icon name="code" size={16} />
        <span>Inline refactor (Coder → Reviewer)</span>
      </header>
      <div className="refactor-body">
        <div className="field">
          <label>File path</label>
          <input className="text-input" value={path} onChange={(e) => setPath(e.target.value)} placeholder="src/core/agent/runner.ts" />
        </div>
        <div className="field">
          <label>Instruction</label>
          <textarea className="text-area" value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="e.g. Add parallel sub-agent delegation" rows={3} />
        </div>
        <div className="field">
          <label>Current content</label>
          <textarea className="text-area mono" value={content} onChange={(e) => setContent(e.target.value)} placeholder="Paste the current file content here" rows={8} />
        </div>
        <div className="refactor-actions">
          <button type="button" className="btn btn-primary" disabled={running} onClick={() => void runRefactor()}>
            {running ? <Icon name="loader" size={14} className="spin" /> : null} Propose & review
          </button>
          {result && (
            <button type="button" className="btn btn-secondary" disabled={running} onClick={() => void applyChange()}>
              Apply change
            </button>
          )}
        </div>
        {result && (
          <div className="refactor-result">
            <Icon name="sub-agent" size={13} />
            <span>{result}</span>
          </div>
        )}
      </div>
    </div>
  );
}
