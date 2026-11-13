import { useEffect, useMemo, useState } from 'react';
import { APP_NAME } from '../../shared/brand';
import { DEMO_PROVIDER_ID, PROVIDER_PRESETS, type ProviderPreset } from '../../shared/defaults';
import type { ModelInfo, ProviderConfig, ProviderDraft, ProviderTestResult, Settings } from '../../shared/types';
import { call } from '../api';
import { Icon } from '../icons';
import { compactNumber, cx, errorText, plural } from '../lib/format';
import { confirmDialog, toast, useStore } from '../store';
import { ProviderAvatar } from './common';
import { KeyValueEditor } from './SettingsParts';
import { Button, IconButton, Modal, Segmented, Switch, TextInput } from './ui';

function toDraft(p: ProviderConfig): ProviderDraft {
  return { id: p.id, name: p.name, kind: p.kind, preset: p.preset, baseUrl: p.baseUrl, headers: p.headers.map((h) => ({ ...h })), models: p.models.map((m) => ({ ...m })), enabled: p.enabled };
}

function fromPreset(preset: ProviderPreset): ProviderDraft {
  return {
    id: `p_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    name: preset.id.startsWith('custom') ? 'My provider' : preset.name,
    kind: preset.kind,
    preset: preset.id,
    baseUrl: preset.baseUrl,
    headers: [],
    models: [],
    enabled: true,
    apiKey: '',
  };
}

function clean(draft: ProviderDraft): ProviderDraft {
  return { ...draft, name: draft.name.trim(), baseUrl: draft.baseUrl.trim(), headers: draft.headers.filter((h) => h.key.trim()) };
}

/* ─────────────────────────────── choosing fetched models ─────────────────────── */

function ModelChooser({ providerName, available, existing, onAdd, onClose }: { providerName: string; available: ModelInfo[]; existing: ModelInfo[]; onAdd: (models: ModelInfo[]) => void; onClose: () => void }) {
  const have = useMemo(() => new Set(existing.map((m) => m.id)), [existing]);
  const [picked, setPicked] = useState<Set<string>>(() => new Set());
  const [query, setQuery] = useState('');
  const q = query.trim().toLowerCase();
  const shown = q ? available.filter((m) => `${m.id} ${m.label ?? ''}`.toLowerCase().includes(q)) : available;
  const fresh = shown.filter((m) => !have.has(m.id));

  const toggle = (id: string): void =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <Modal title={`Models from ${providerName}`} onClose={onClose} width={520}
      footer={
        <>
          <span className="muted grow">{plural(available.length, 'model')} available</span>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!picked.size} onClick={() => { onAdd(available.filter((m) => picked.has(m.id))); onClose(); }}>
            {picked.size ? `Add ${plural(picked.size, 'model')}` : 'Add models'}
          </Button>
        </>
      }>
      <div className="chooser-tools">
        <div className="menu-search">
          <Icon name="search" size={14} />
          <input value={query} placeholder="Filter models" spellCheck={false} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <Button size="sm" variant="ghost" disabled={!fresh.length} onClick={() => setPicked(new Set([...picked, ...fresh.map((m) => m.id)]))}>
          Select all
        </Button>
      </div>
      <div className="chooser-list">
        {shown.map((m) => {
          const added = have.has(m.id);
          const on = added || picked.has(m.id);
          return (
            <button key={m.id} type="button" role="checkbox" aria-checked={on} disabled={added} className={cx('chooser-item', on && 'on')} onClick={() => toggle(m.id)}>
              <span className="checkbox">{on && <Icon name="check" size={12} strokeWidth={2.4} />}</span>
              <span className="mono truncate grow">{m.id}</span>
              {m.contextWindow ? <span className="muted">{compactNumber(m.contextWindow)} ctx</span> : null}
              {added && <span className="muted">added</span>}
            </button>
          );
        })}
        {!shown.length && <div className="set-empty">No models match.</div>}
      </div>
    </Modal>
  );
}

/* ─────────────────────────────────── gallery ─────────────────────────────────── */

function PresetGallery({ onPick, onClose }: { onPick: (preset: ProviderPreset) => void; onClose: () => void }) {
  return (
    <Modal title="Add a provider" onClose={onClose} width={640}>
      <p className="gallery-intro">Pick a service to pre-fill its address, or choose a custom endpoint. Anything that speaks the OpenAI Chat Completions or Anthropic Messages format works — including local servers and gateways.</p>
      <div className="gallery">
        {PROVIDER_PRESETS.map((preset) => (
          <button key={preset.id} type="button" className="gallery-item" onClick={() => onPick(preset)}>
            <ProviderAvatar provider={{ preset: preset.id, kind: preset.kind, name: preset.name.replace(/^Custom \(/, '') }} size={28} />
            <span className="gallery-text">
              <b>{preset.name}</b>
              <span>{preset.hint}</span>
            </span>
          </button>
        ))}
      </div>
    </Modal>
  );
}

/* ─────────────────────────────────── the form ────────────────────────────────── */

interface FormProps {
  draft: ProviderDraft;
  setDraft: (draft: ProviderDraft) => void;
  stored: ProviderConfig | undefined;
  isNew: boolean;
  dirty: boolean;
  onSaved: (id: string, saved: ProviderConfig | undefined) => void;
  onDiscard: () => void;
  onDeleted: () => void;
}

function ProviderForm({ draft, setDraft, stored, isNew, dirty, onSaved, onDiscard, onDeleted }: FormProps) {
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<ProviderTestResult | null>(null);
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState<ModelInfo[] | null>(null);
  const [newModel, setNewModel] = useState('');
  const preset = PROVIDER_PRESETS.find((p) => p.id === draft.preset);
  const keepsStoredKey = Boolean(stored?.hasKey) && draft.apiKey === undefined;

  useEffect(() => {
    setTest(null);
    setShowKey(false);
    setNewModel('');
  }, [draft.id]);

  const patch = (p: Partial<ProviderDraft>): void => {
    setDraft({ ...draft, ...p });
    setTest(null);
  };
  const patchModel = (id: string, p: Partial<ModelInfo>): void => patch({ models: draft.models.map((m) => (m.id === id ? { ...m, ...p } : m)) });
  const addModels = (models: ModelInfo[]): void => {
    const have = new Set(draft.models.map((m) => m.id));
    patch({ models: [...draft.models, ...models.filter((m) => m.id && !have.has(m.id))] });
  };

  const save = async (): Promise<void> => {
    if (!draft.name.trim()) return toast('error', 'Give the provider a name.');
    if (!draft.baseUrl.trim()) return toast('error', 'Enter the base URL of the API.');
    setSaving(true);
    try {
      const next = await call('provider.save', { provider: clean(draft) });
      useStore.setState({ settings: next });
      toast('success', draft.models.length ? `${draft.name.trim()} saved` : `${draft.name.trim()} saved. Add at least one model to use it.`);
      onSaved(draft.id, next.providers.find((p: any) => p.id === draft.id));
    } catch (err: any) {
      toast('error', errorText(err));
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (): Promise<void> => {
    setTesting(true);
    setTest(null);
    try {
      setTest(await call('provider.test', { provider: clean(draft), modelId: draft.models[0]?.id }));
    } catch (err: any) {
      setTest({ ok: false, latencyMs: 0, message: errorText(err) });
    } finally {
      setTesting(false);
    }
  };

  const fetchModels = async (): Promise<void> => {
    setFetching(true);
    try {
      const { models } = await call('provider.fetchModels', { provider: clean(draft) });
      if (!models.length) toast('info', 'The provider returned an empty model list. Add model ids by hand below.');
      else setFetched(models);
    } catch (err: any) {
      toast('error', errorText(err));
    } finally {
      setFetching(false);
    }
  };

  return (
    <div className="provider-form">
      <header className="provider-form-head">
        <ProviderAvatar provider={draft} size={34} />
        <div className="grow">
          <h2>{draft.name.trim() || 'New provider'}</h2>
          <p>{isNew ? 'Not saved yet' : stored?.hasKey ? 'Key stored' : preset?.local ? 'Local server — no key needed' : 'No API key stored'}</p>
        </div>
        <label className="inline-switch">
          <span>{draft.enabled ? 'Enabled' : 'Disabled'}</span>
          <Switch checked={draft.enabled} label="Enabled" onChange={(enabled) => patch({ enabled })} />
        </label>
      </header>

      <div className="form-grid name-and-format">
        <label className="field">
          <span>Name</span>
          <TextInput value={draft.name} placeholder="My provider" onChange={(value) => patch({ name: value })} />
        </label>
        <div className="field">
          <span>API format</span>
          <Segmented
            value={draft.kind === 'anthropic' ? 'anthropic' : 'openai'}
            options={[
              { value: 'openai', label: 'OpenAI-compatible', tip: 'POST {base URL}/chat/completions' },
              { value: 'anthropic', label: 'Anthropic-compatible', tip: 'POST {base URL}/v1/messages' },
            ]}
            onChange={(kind) => patch({ kind: kind as any })}
          />
        </div>
      </div>

      <label className="field">
        <span>Base URL</span>
        <TextInput mono value={draft.baseUrl} placeholder={draft.kind === 'anthropic' ? 'https://api.anthropic.com' : 'https://api.example.com/v1'} onChange={(value) => patch({ baseUrl: value })} />
        <small>{draft.kind === 'anthropic' ? 'Requests go to {base URL}/v1/messages. A trailing /v1 is fine.' : 'Requests go to {base URL}/chat/completions, so most services need the /v1 suffix.'}</small>
      </label>

      <div className="field">
        <span>
          API key
          {preset?.keyUrl && (
            <a href={preset.keyUrl} target="_blank" rel="noreferrer noopener" className="field-link">
              Get a key <Icon name="external" size={11} />
            </a>
          )}
        </span>
        {keepsStoredKey ? (
          <div className="key-stored">
            <Icon name="key" size={14} />
            <span className="mono grow">{stored?.keyPreview ?? '••••••••'}</span>
            <Button size="sm" variant="ghost" onClick={() => patch({ apiKey: '' })}>Replace</Button>
          </div>
        ) : (
          <div className="key-input">
            <TextInput mono type={showKey ? 'text' : 'password'} value={draft.apiKey ?? ''} placeholder={preset?.local ? 'Not needed for local servers' : 'Paste your key'} onChange={(value) => patch({ apiKey: value })} />
            <IconButton icon={showKey ? 'eye-off' : 'eye'} label={showKey ? 'Hide key' : 'Show key'} onClick={() => setShowKey(!showKey)} />
            {stored?.hasKey && (
              <Button size="sm" variant="ghost" onClick={() => patch({ apiKey: undefined })}>Keep current</Button>
            )}
          </div>
        )}
        <small>Stored on this machine only and sent to nothing but this provider.{stored?.hasKey && draft.apiKey === '' ? ' Saving with an empty field removes the stored key.' : ''}</small>
      </div>

      <div className="field">
        <span>Models</span>
        {draft.models.length > 0 ? (
          <div className="model-table">
            <div className="model-table-head">
              <span>Model id</span>
              <span>Display name</span>
              <span>Context window</span>
              <span />
            </div>
            {draft.models.map((m) => (
              <div key={m.id} className="model-table-row">
                <span className="mono truncate selectable" title={m.id}>{m.id}</span>
                <TextInput value={m.label ?? ''} placeholder="Optional" onChange={(value) => patchModel(m.id, { label: value || undefined })} />
                <TextInput mono inputMode="numeric" value={m.contextWindow ? String(m.contextWindow) : ''} placeholder="tokens" onChange={(value) => {
                  const n = Number(value.replace(/[^\d]/g, ''));
                  patchModel(m.id, { contextWindow: n > 0 ? n : undefined });
                }} />
                <IconButton icon="x" label="Remove model" tip={false} onClick={() => patch({ models: draft.models.filter((x) => x.id !== m.id) })} />
              </div>
            ))}
          </div>
        ) : (
          <div className="model-empty">No models yet. Fetch the list from the provider, or type a model id.</div>
        )}
        <div className="model-add">
          <Button icon="download" busy={fetching} disabled={!draft.baseUrl.trim()} onClick={() => void fetchModels()}>Fetch models</Button>
          <form className="model-add-manual" onSubmit={(e) => {
            e.preventDefault();
            const id = newModel.trim();
            if (!id) return;
            addModels([{ id }]);
            setNewModel('');
          }}>
            <TextInput mono value={newModel} placeholder="or type a model id" onChange={(value) => setNewModel(value)} />
            <Button type="submit" disabled={!newModel.trim()}>Add</Button>
          </form>
        </div>
        <small>The context window is optional; it powers the context gauge and trims long conversations earlier for small models.</small>
      </div>

      <details className="advanced" open={draft.headers.length > 0}>
        <summary>
          <Icon name="chevron-right" size={12} className="caret" />
          Extra request headers
        </summary>
        <div className="advanced-body">
          <KeyValueEditor pairs={draft.headers} onChange={(headers) => patch({ headers })} keyPlaceholder="Header" valuePlaceholder="Value" addLabel="Add header" />
          <small>Sent with every request to this provider. Values are left out of settings exports.</small>
        </div>
      </details>

      {test && (
        <div className={cx('test-result selectable', test.ok ? 'ok' : 'fail')}>
          <Icon name={test.ok ? 'circle-check' : 'alert'} size={15} />
          <div>
            <b>{test.ok ? `Connected${test.latencyMs ? ` in ${test.latencyMs} ms` : ''}` : 'Connection failed'}</b>
            <span>{test.message}</span>
            {test.ok && test.reply && <span className="mono">Reply: {test.reply}</span>}
          </div>
        </div>
      )}

      <footer className="provider-form-foot">
        {!isNew && (
          <Button variant="ghost" icon="trash" onClick={() =>
            confirmDialog({
              title: `Delete ${stored?.name ?? 'this provider'}?`,
              body: 'The provider, its models and its stored API key are removed.',
              confirmLabel: 'Delete provider',
              danger: true,
              onConfirm: async () => {
                try {
                  const next = await call('provider.remove', { id: draft.id });
                  useStore.setState({ settings: next });
                  onDeleted();
                } catch (err: any) {
                  toast('error', errorText(err));
                }
              },
            })
          }>Delete</Button>
        )}
        <span className="grow" />
        {dirty && (
          <Button variant="ghost" onClick={onDiscard}>{isNew ? 'Cancel' : 'Discard changes'}</Button>
        )}
        <Button icon="zap" busy={testing} disabled={!draft.baseUrl.trim()} onClick={() => void runTest()} data-tip={draft.models.length ? `Sends a one-word prompt to ${draft.models[0].id}` : 'Checks that the model list can be read'}>
          Test connection
        </Button>
        <Button variant="primary" busy={saving} disabled={!dirty} onClick={() => void save()}>{isNew ? 'Add provider' : 'Save'}</Button>
      </footer>

      {fetched && <ModelChooser providerName={draft.name.trim() || 'provider'} available={fetched} existing={draft.models} onAdd={addModels} onClose={() => setFetched(null)} />}
    </div>
  );
}

function DemoForm({ provider }: { provider: ProviderConfig }) {
  const toggle = async (enabled: boolean): Promise<void> => {
    try {
      const next = await call('provider.save', { provider: { ...toDraft(provider), enabled } });
      useStore.setState({ settings: next });
    } catch (err: any) {
      toast('error', errorText(err));
    }
  };
  return (
    <div className="provider-form">
      <header className="provider-form-head">
        <ProviderAvatar provider={provider} size={34} />
        <div className="grow">
          <h2>{provider.name}</h2>
          <p>Built in · no network, no key</p>
        </div>
        <label className="inline-switch">
          <span>{provider.enabled ? 'Enabled' : 'Disabled'}</span>
          <Switch checked={provider.enabled} label="Enabled" onChange={(v) => void toggle(v)} />
        </label>
      </header>
      <div className="demo-explain">
        <p>The demo model is a script, not an AI. It plays back a realistic run so you can try the interface before connecting anything.</p>
        <p>It ignores what you type. Disable it once a real provider is set up.</p>
      </div>
    </div>
  );
}

/* ─────────────────────────────────── section ─────────────────────────────────── */

export function ProvidersSection({ settings }: { settings: Settings }) {
  const providers = settings.providers;
  const [selectedId, setSelectedId] = useState<string>(() => providers.find((p: any) => p.id !== DEMO_PROVIDER_ID)?.id ?? DEMO_PROVIDER_ID);
  const [draft, setDraft] = useState<ProviderDraft | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [gallery, setGallery] = useState(false);

  const stored = providers.find((p: any) => p.id === selectedId);
  const base = useMemo(() => (stored ? toDraft(stored) : null), [stored]);
  const baseKey = base ? JSON.stringify(base) : '';

  useEffect(() => {
    if (!isNew) setDraft(base);
  }, [selectedId, baseKey, isNew]);

  const dirty = Boolean(draft) && (isNew || JSON.stringify(clean(draft as ProviderDraft)) !== baseKey);

  const leave = (action: () => void): void => {
    if (!dirty) return action();
    confirmDialog({
      title: 'Discard unsaved changes?',
      body: `Your edits to ${draft?.name.trim() || 'this provider'} have not been saved.`,
      confirmLabel: 'Discard',
      danger: true,
      onConfirm: action,
    });
  };

  const select = (id: string): void =>
    leave(() => {
      setIsNew(false);
      setSelectedId(id);
    });

  const startNew = (preset: ProviderPreset): void => {
    const fresh = fromPreset(preset);
    setGallery(false);
    setIsNew(true);
    setSelectedId(fresh.id);
    setDraft(fresh);
  };

  return (
    <div className="providers">
      <div className="provider-list">
        {isNew && draft && (
          <div className="provider-item active">
            <ProviderAvatar provider={draft} size={24} />
            <span className="provider-item-text">
              <b className="truncate">{draft.name.trim() || 'New provider'}</b>
              <span>Not saved yet</span>
            </span>
          </div>
        )}
        {providers.map((p: any) => (
          <button key={p.id} type="button" className={cx('provider-item', !isNew && p.id === selectedId && 'active', !p.enabled && 'off')} onClick={() => select(p.id)}>
            <ProviderAvatar provider={p} size={24} />
            <span className="provider-item-text">
              <b className="truncate">{p.name}</b>
              <span>{!p.enabled ? 'Disabled' : p.kind === 'demo' ? 'Simulated' : p.models.length ? plural(p.models.length, 'model') : 'No models yet'}</span>
            </span>
            {p.kind !== 'demo' && p.enabled && !p.models.length && <Icon name="alert" size={13} className="text-amber" />}
          </button>
        ))}
        <Button icon="plus" className="provider-add" onClick={() => leave(() => setGallery(true))}>Add provider</Button>
      </div>

      <div className="provider-detail">
        {stored?.kind === 'demo' && !isNew ? (
          <DemoForm provider={stored} />
        ) : draft ? (
          <ProviderForm
            key={draft.id}
            draft={draft}
            setDraft={setDraft}
            stored={isNew ? undefined : stored}
            isNew={isNew}
            dirty={dirty}
            onSaved={(id: string, saved: any) => {
              setIsNew(false);
              setSelectedId(id);
              if (saved) setDraft(toDraft(saved));
            }}
            onDiscard={() => {
              if (isNew) {
                setIsNew(false);
                setSelectedId(providers.find((p: any) => p.id !== DEMO_PROVIDER_ID)?.id ?? DEMO_PROVIDER_ID);
              } else setDraft(base);
            }}
            onDeleted={() => setSelectedId(providers.find((p: any) => p.id !== DEMO_PROVIDER_ID && p.id !== selectedId)?.id ?? DEMO_PROVIDER_ID)}
          />
        ) : (
          <div className="set-empty">Select a provider, or add one.</div>
        )}
      </div>

      {gallery && <PresetGallery onPick={startNew} onClose={() => setGallery(false)} />}
    </div>
  );
}

/* ─────────────────────────────────── settings shell ──────────────────────────── */

const NAV: { id: string; label: string; icon: string; title: string; blurb: string }[] = [
  { id: 'general', label: 'General', icon: 'sliders', title: 'General', blurb: 'How the app behaves day to day.' },
  { id: 'providers', label: 'Providers', icon: 'plug', title: 'Providers', blurb: 'Connect any OpenAI-compatible or Anthropic-compatible endpoint with a base URL and an API key.' },
  { id: 'models', label: 'Models', icon: 'cpu', title: 'Models', blurb: 'Choose which model leads, which ones help, and how far a run may go.' },
  { id: 'agents', label: 'Sub-agents', icon: 'workflow', title: 'Sub-agents', blurb: 'Specialists the lead agent can hand work to.' },
  { id: 'appearance', label: 'Appearance', icon: 'palette', title: 'Appearance', blurb: 'Theme, accent colour and text size.' },
];

export function SettingsScreen({ section }: { section: string }) {
  const settings = useStore((s) => s.settings);
  const current = NAV.find((n) => n.id === section) ?? NAV[0];

  return (
    <div className="settings">
      <nav className="settings-nav" aria-label="Settings">
        <header className="pane-header">
          <button type="button" className="back-btn" onClick={() => {
            import('../store').then(({ closeSettings }) => closeSettings());
          }}>
            <Icon name="arrow-left" size={15} />
            Back to app
          </button>
        </header>
        <div className="settings-nav-list">
          <div className="sidebar-label"><span>Settings</span></div>
          {NAV.map((n) => (
            <button key={n.id} type="button" className={cx('side-nav', n.id === section && 'active')} aria-current={n.id === section ? 'page' : undefined} onClick={() => {
              import('../store').then(({ openSettings }) => openSettings(n.id));
            }}>
              <Icon name={n.icon} size={15} />
              <span className="grow">{n.label}</span>
            </button>
          ))}
        </div>
      </nav>
      <div className="settings-main">
        <header className="pane-header settings-header" />
        <div className="settings-scroll">
          <div className="settings-content">
            <div className="settings-title">
              <h1>{current.title}</h1>
              {current.blurb && <p>{current.blurb}</p>}
            </div>
            {section === 'providers' && <ProvidersSection settings={settings} />}
            {section !== 'providers' && (
              <div className="set-empty">
                <Icon name="settings" size={32} />
                <p>{current.title} section coming soon — configure providers first.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
