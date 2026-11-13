export async function call<M extends string>(method: M, params?: any): Promise<any> {
  const api = (window as any).batonApi;
  if (!api || typeof api.invoke !== 'function') {
    throw new Error('Desktop API is not available in this context.');
  }
  return api.invoke(method, params);
}

export function isDesktop(): boolean {
  return typeof window !== 'undefined' && !!(window as any).batonApi;
}

export function openEvents(_opts: any): any {
  // Event subscription hook for real-time updates; no-op in minimal harness.
  return () => {};
}

export const platformHint: string =
  typeof navigator !== 'undefined' && navigator.userAgent
    ? (navigator.platform ?? 'unknown')
    : 'unknown';
