import { useEffect } from 'react';

export function applyAppearance(settings: any): void {
  const a = settings?.appearance ?? {};
  const root = document.documentElement;
  root.dataset.theme = a.theme === 'system' ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : a.theme;
  root.dataset.density = a.density ?? 'comfortable';
  root.style.setProperty('--accent', a.accent ?? '#8e7dff');
  root.style.setProperty('--font-scale', String(a.fontScale ?? 1));
}
