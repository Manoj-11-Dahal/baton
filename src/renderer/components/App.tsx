import { APP_NAME } from '../../shared/brand';
import { Icon } from '../icons';
import { cx } from '../lib/format';
import { openSettings, togglePanel, toggleSidebar, useStore, type State } from '../store';
import { TaskBoard } from './TaskBoard';
import { ActivityFeed } from './TaskBoard';
import { RefactorPanel } from './RefactorPanel';
import { SettingsScreen } from './Settings';

export function App() {
  const settingsSection = useStore((s: State) => s.settingsSection);
  const panelOpen = useStore((s: State) => s.panelOpen);
  const panelTab = useStore((s: State) => s.panelTab);

  if (settingsSection) {
    return <SettingsScreen section={settingsSection} />;
  }

  return (
    <div className={cx('app', 'desktop', !useStore.getState().sidebarOpen && 'sidebar-closed')}>
      <aside className="sidebar">
        <Sidebar />
      </aside>
      <main className="main">
        <MainHeader />
        <NewThreadScreen />
        {panelOpen && <SidePanel tab={panelTab} />}
      </main>
    </div>
  );
}

function SidePanel({ tab }: { tab: string }) {
  return (
    <aside className="side-panel">
      <header className="pane-header side-panel-header">
        <button type="button" className="icon-btn" aria-label="Close panel" onClick={() => togglePanel()}>
          <Icon name="panel-left" size={16} />
        </button>
        <span className="grow side-panel-title">{tab === 'activity' ? 'Activity' : tab === 'refactor' ? 'Refactor' : 'Tasks'}</span>
        <div className="side-panel-tabs">
          <button type="button" className={cx('side-panel-tab', tab === 'tasks' && 'active')} onClick={() => setPanelTab('tasks')}>Tasks</button>
          <button type="button" className={cx('side-panel-tab', tab === 'activity' && 'active')} onClick={() => setPanelTab('activity')}>Activity</button>
          <button type="button" className={cx('side-panel-tab', tab === 'refactor' && 'active')} onClick={() => setPanelTab('refactor')}>Refactor</button>
        </div>
      </header>
      <div className="side-panel-body">
        {tab === 'tasks' && <TaskBoard />}
        {tab === 'activity' && <ActivityFeed />}
        {tab === 'refactor' && <RefactorPanel />}
      </div>
    </aside>
  );
}

function Sidebar() {
  const settingsSection = useStore((s: State) => s.settingsSection);
  const mod = modKey({ platform: 'linux' });

  return (
    <>
      <header className="pane-header sidebar-header">
        <div className="brand">
          <Icon name="bot" size={17} strokeWidth={2.2} className="brand-mark" />
          <span>{APP_NAME}</span>
        </div>
        <span className="grow" />
        <button type="button" className="icon-btn" aria-label="New thread" onClick={() => {}}>
          <Icon name="pencil" size={16} />
        </button>
        <button type="button" className="icon-btn" aria-label="Hide sidebar" onClick={toggleSidebar}>
          <Icon name="sidebar" size={16} />
        </button>
      </header>

      <div className="sidebar-search">
        <Icon name="search" size={14} />
        <input placeholder="Search threads" spellCheck={false} />
      </div>

      <div className="sidebar-scroll">
        <div className="sidebar-label"><span>Workspaces</span></div>
        <div className="ws-row">
          <Icon name="folder" size={14} className="ws-icon" />
          <span className="ws-name">Scratchpad</span>
        </div>
      </div>

      <footer className="sidebar-footer">
        <button type="button" className={cx('side-nav', settingsSection !== null && 'active')} onClick={() => openSettings('general')}>
          <Icon name="settings" size={15} />
          <span className="grow">Settings</span>
        </button>
      </footer>
    </>
  );
}

function MainHeader() {
  return (
    <header className="pane-header main-header">
      <button type="button" className="icon-btn" aria-label="Show sidebar" onClick={toggleSidebar}>
        <Icon name="sidebar" size={16} />
      </button>
      <button type="button" className="icon-btn" aria-label="New thread" onClick={() => {}}>
        <Icon name="pencil" size={16} />
      </button>
      <div className="header-title">
        <span className="title-btn muted">New thread</span>
      </div>
      <span className="grow drag-fill" />
      <button type="button" className="icon-btn" aria-label="Show side panel" onClick={() => togglePanel()}>
        <Icon name="panel-right" size={16} />
      </button>
    </header>
  );
}

function NewThreadScreen() {
  const settings = useStore((s) => s.settings);
  const demo = !settings.providers.some((p: any) => p.kind !== 'demo' && p.enabled && p.models.length > 0);

  return (
    <div className="new-thread">
      <div className="new-thread-inner">
        <div className="hero">
          <span className="hero-mark">
            <Icon name="bot" size={26} strokeWidth={2.2} />
          </span>
          <h1>What should we work on?</h1>
          <p>
            {APP_NAME} plans the work, uses tools in your workspace, and hands independent tasks to sub-agents that run in parallel.
          </p>
        </div>

        <div className="new-thread-ws">
          <span className="muted">Working in</span>
          <span className="ws-pill">
            <Icon name="folder" size={14} />
            <span className="truncate">Scratchpad</span>
          </span>
        </div>

        <textarea className="composer" rows={4} placeholder="Ask anything…" value="" readOnly />

        <div className="starters">
          {[{ icon: 'compass', label: 'Explain this project' }, { icon: 'scan', label: 'Review my changes' }, { icon: 'flask', label: 'Write tests' }].map((s) => (
            <button key={s.label} type="button" className="starter" onClick={() => {}}>
              <Icon name={s.icon} size={14} />
              {s.label}
            </button>
          ))}
        </div>

        {demo && (
          <button type="button" className="demo-card" onClick={() => openSettings('providers')}>
            <Icon name="sparkles" size={30} />
            <span className="demo-card-text">
              <b>You are on the offline demo model</b>
              <span>Connect OpenAI, Anthropic, Ollama or any compatible endpoint to do real work.</span>
            </span>
            <span className="demo-card-cta">
              Connect a model
              <Icon name="arrow-right" size={13} />
            </span>
          </button>
        )}
      </div>
      <span className="sr-only">{APP_NAME}</span>
    </div>
  );
}

function modKey(env: { platform: string }): string {
  return env.platform === 'darwin' ? '⌘' : 'Ctrl';
}

function setPanelTab(tab: string): void {
  useStore.getState();
  import('../store').then(({ setPanelTab: spt }) => spt(tab));
}
