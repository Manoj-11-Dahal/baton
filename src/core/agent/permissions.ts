export function enabledAgents(settings: any): any[] {
  return (settings.agents ?? []).filter((a: any) => a.enabled);
}
