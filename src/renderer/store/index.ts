import { create } from 'zustand';
import type { Settings, SettingsPatch } from '../../shared/types';
import { defaultSettings } from '../../shared/defaults';
import { applyAppearance } from './appearance';

export interface Toast {
  id: number;
  kind: 'info' | 'success' | 'error';
  text: string;
}

export interface Dialog {
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void | Promise<void>;
}

export interface Compose {
  model: { providerId: string; modelId: string } | null;
  mode: 'agent' | 'plan' | 'chat';
  approval: 'ask' | 'auto-edit' | 'full-auto';
}

export interface State {
  phase: 'loading' | 'ready' | 'error';
  bootError: string;
  online: boolean;
  settings: Settings;
  settingsSection: string | null;
  toasts: Toast[];
  compose: Compose;
  sidebarOpen: boolean;
  panelOpen: boolean;
  panelTab: string;
  activeThreadId: string | null;
  dialog: Dialog | null;
}

export const useStore = create<State>(() => ({
  phase: 'loading',
  bootError: '',
  online: true,
  settings: defaultSettings(),
  settingsSection: null,
  toasts: [],
  compose: { model: null, mode: 'agent', approval: 'ask' },
  sidebarOpen: true,
  panelOpen: false,
  panelTab: 'changes',
  activeThreadId: null,
  dialog: null,
}));

let toastId = 0;

export function toast(kind: Toast['kind'], text: string): void {
  const id = ++toastId;
  useStore.setState((s) => ({ toasts: [...s.toasts.slice(-3), { id, kind, text }] }));
  setTimeout(() => dismissToast(id), kind === 'error' ? 8000 : 3500);
}

export function dismissToast(id: number): void {
  useStore.setState((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
}

export function confirmDialog(options: { title: string; body: string; confirmLabel: string; danger?: boolean; onConfirm: () => void | Promise<void> }): void {
  useStore.setState({ dialog: options });
}

export function closeDialog(): void {
  useStore.setState({ dialog: null });
}

export async function attempt<T>(action: () => Promise<T>): Promise<T | undefined> {
  try {
    return await action();
  } catch (err) {
    toast('error', errorText(err));
    return undefined;
  }
}

export function errorText(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

export function updateSettings(patch: SettingsPatch): Promise<boolean> {
  // This will be replaced by the real IPC-backed version when wiring is complete.
  return Promise.resolve(false);
}

export function openSettings(section: string = 'providers'): void {
  useStore.setState({ settingsSection: section });
}

export function closeSettings(): void {
  useStore.setState({ settingsSection: null });
}

export function toggleSidebar(): void {
  useStore.setState((s) => ({ sidebarOpen: !s.sidebarOpen }));
}

export function togglePanel(tab?: string): void {
  useStore.setState((s) => (tab && (!s.panelOpen || s.panelTab !== tab) ? { panelOpen: true, panelTab: tab } : { panelOpen: !s.panelOpen }));
}

export function setPanelTab(tab: string): void {
  useStore.setState({ panelTab: tab, panelOpen: true });
}

export function applyAppearanceFromSettings(settings: Settings): void {
  applyAppearance(settings);
}
