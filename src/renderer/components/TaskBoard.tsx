import { useMemo, useState } from 'react';
import { Icon } from '../icons';
import { cx, plural } from '../lib/format';
import { useStore } from '../store';

type TaskStatus = 'todo' | 'in_progress' | 'done' | 'blocked';

interface TaskItem {
  id: string;
  title: string;
  status: TaskStatus;
  agent?: string;
  agentColor?: string;
  createdAt: number;
  updatedAt: number;
  parentId?: string;
}

const STATUS_LABEL: Record<TaskStatus, string> = {
  todo: 'To do',
  in_progress: 'In progress',
  done: 'Done',
  blocked: 'Blocked',
};

const STATUS_ICON: Record<TaskStatus, string> = {
  todo: 'circle',
  in_progress: 'status-running',
  done: 'circle-check',
  blocked: 'alert',
};

const COLUMN_ORDER: TaskStatus[] = ['todo', 'in_progress', 'done', 'blocked'];

const DEFAULT_TASKS: TaskItem[] = [
  { id: 't1', title: 'Explore workspace structure', status: 'todo', agent: 'explorer', createdAt: Date.now() - 100000, updatedAt: Date.now() - 100000 },
  { id: 't2', title: 'Write failing tests', status: 'todo', agent: 'tester', createdAt: Date.now() - 90000, updatedAt: Date.now() - 90000 },
  { id: 't3', title: 'Implement feature', status: 'in_progress', agent: 'coder', createdAt: Date.now() - 80000, updatedAt: Date.now() - 60000 },
  { id: 't4', title: 'Review changes', status: 'todo', agent: 'reviewer', createdAt: Date.now() - 70000, updatedAt: Date.now() - 70000 },
];

export function TaskBoard() {
  const [tasks, setTasks] = useState<TaskItem[]>(DEFAULT_TASKS);
  const byStatus = useMemo(() => {
    const map: Record<TaskStatus, TaskItem[]> = { todo: [], in_progress: [], done: [], blocked: [] };
    for (const t of tasks) map[t.status].push(t);
    return map;
  }, [tasks]);

  const setStatus = (id: string, status: TaskStatus): void => {
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, status, updatedAt: Date.now() } : t)));
  };

  const addTask = (title: string): void => {
    const now = Date.now();
    setTasks((prev) => [...prev, { id: `t_${now}`, title, status: 'todo', createdAt: now, updatedAt: now }]);
  };

  return (
    <div className="task-board">
      <header className="task-board-header">
        <span className="task-board-title">Task board</span>
        <div className="task-board-actions">
          <button type="button" className="task-add-btn" onClick={() => addTask('New task')}>
            <Icon name="plus" size={13} />
            Add task
          </button>
        </div>
      </header>
      <div className="task-board-columns">
        {COLUMN_ORDER.map((status) => (
          <div key={status} className="task-column">
            <div className="task-column-head">
              <Icon name={STATUS_ICON[status]} size={13} />
              <span className="task-column-label">{STATUS_LABEL[status]}</span>
              <span className="task-column-count">{byStatus[status].length}</span>
            </div>
            <div className="task-column-body">
              {byStatus[status].map((t) => (
                <div key={t.id} className={cx('task-card', `task-card-${t.status}`)} onClick={() => setStatus(t.id, status === 'done' ? 'todo' : status === 'todo' ? 'in_progress' : 'done')}>
                  <span className="task-card-title">{t.title}</span>
                  {t.agent && (
                    <span className="task-card-agent">
                      <Icon name="sub-agent" size={11} className="task-card-agent-icon" style={{ color: agentColor(t.agentColor ?? 'slate') }} />
                      {t.agent}
                    </span>
                  )}
                </div>
              ))}
              {byStatus[status].length === 0 && <div className="task-empty">None</div>}
            </div>
          </div>
        ))}
      </div>
      <footer className="task-board-foot">
        <span>{plural(tasks.length, 'task')} tracked</span>
      </footer>
    </div>
  );
}

function agentColor(c: string): string {
  const tints: Record<string, string> = {
    sky: '#4aa8ff',
    violet: '#8e7dff',
    amber: '#f0a63a',
    rose: '#ec6aa0',
    emerald: '#35c99a',
    slate: '#7d8590',
    cyan: '#3bc9db',
    orange: '#ff9e5a',
  };
  return tints[c] ?? c;
}

/* ─────────────────────────────────── activity feed ───────────────────────────── */

interface ActivityEntry {
  id: string;
  kind: 'agent' | 'tool' | 'system' | 'subagent';
  title: string;
  detail?: string;
  time: number;
  agent?: string;
  agentColor?: string;
  status?: 'running' | 'done' | 'error';
}

const ACTIVITY: ActivityEntry[] = [
  { id: 'a1', kind: 'subagent', title: 'Coder started "Implement feature"', detail: 'delegated from lead agent', time: Date.now() - 70000, agent: 'coder', status: 'done' },
  { id: 'a2', kind: 'tool', title: 'edit_file: src/core/agent/runner.ts', detail: 'added orchestrate tool', time: Date.now() - 60000 },
  { id: 'a3', kind: 'agent', title: 'Lead agent planned work', detail: '4 steps created', time: Date.now() - 50000 },
  { id: 'a4', kind: 'subagent', title: 'Reviewer started "Review changes"', detail: 'handoff from coder', time: Date.now() - 30000, agent: 'reviewer', status: 'running' },
];

export function ActivityFeed() {
  return (
    <div className="activity-feed">
      <header className="activity-feed-header">
        <span className="activity-feed-title">Activity</span>
      </header>
      <div className="activity-feed-list">
        {ACTIVITY.map((e) => (
          <div key={e.id} className={cx('activity-item', `activity-${e.kind}`)}>
            <div className="activity-line">
              <span className="activity-icon">
                <Icon name={e.kind === 'subagent' ? 'sub-agent' : e.kind === 'agent' ? 'bot' : e.kind === 'tool' ? 'code' : 'alert'} size={12} />
              </span>
              <div className="activity-content">
                <span className="activity-title">{e.title}</span>
                {e.detail && <span className="activity-detail">{e.detail}</span>}
                {e.agent && (
                  <span className="activity-agent" style={{ color: agentColor(e.agentColor ?? 'slate') }}>
                    <Icon name="sub-agent" size={10} /> {e.agent}
                  </span>
                )}
                {e.status && <span className={`activity-status activity-${e.status}`}>{e.status}</span>}
              </div>
              <span className="activity-time">{timeAgo(e.time)}</span>
            </div>
            {e.id !== ACTIVITY[ACTIVITY.length - 1].id && <div className="activity-divider" />}
          </div>
        ))}
      </div>
    </div>
  );
}

function timeAgo(timestamp: number): string {
  const secs = Math.floor((Date.now() - timestamp) / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  return `${mins}m ago`;
}
