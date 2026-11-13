import type { ProviderConfig } from '../../shared/types';
import { PROVIDER_PRESETS } from '../../shared/defaults';
import { Icon } from '../icons';
import { cx } from '../lib/format';
import { useState } from 'react';

export function ProviderAvatar({ provider, size = 24 }: { provider: ProviderConfig | { preset?: string; kind?: string; name?: string }; size?: number }) {
  const preset = provider.preset ? PROVIDER_PRESETS.find((p) => p.id === provider.preset) : undefined;
  const tint = preset?.tint ?? '#7d8590';
  const letter = (provider.name ?? 'P').charAt(0).toUpperCase();
  return (
    <span className="avatar" style={{ width: size, height: size, background: tint, color: '#fff' }}>
      <span className="avatar-letter">{letter}</span>
    </span>
  );
}

export function agentStyle(color: string): Record<string, string> {
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
  return { color: tints[color] ?? color };
}

export function DiffView({ patch }: { patch: string }) {
  return <pre className="diff-view selectable">{patch}</pre>;
}

export function Elapsed({ since }: { since: number }) {
  return <span className="elapsed">{Math.max(0, Date.now() - since)} ms</span>;
}

export function EmptyState({ icon, title, action }: { icon: string; title: string; action?: React.ReactNode }) {
  return (
    <div className="empty-state">
      <Icon name={icon} size={32} />
      <h3>{title}</h3>
      {action && <div className="empty-action">{action}</div>}
    </div>
  );
}

export function CopyButton({ text, label, className }: { text: string; label: string; className?: string }) {
  return (
    <button type="button" className={cx('copy-btn', className)} aria-label={label} title={label}>
      <Icon name="copy" size={13} />
    </button>
  );
}

export function Disclosure({ title, meta, defaultOpen, children }: { title: string; meta?: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen ?? true);
  return (
    <div className="disclosure">
      <button type="button" className="disclosure-head" onClick={() => setOpen((o) => !o)}>
        <span>{title}</span>
        {meta && <span className="disclosure-meta">{meta}</span>}
        <Icon name={open ? 'chevron-down' : 'chevron-right'} size={12} className="caret" />
      </button>
      {open && <div className="disclosure-body">{children}</div>}
    </div>
  );
}
