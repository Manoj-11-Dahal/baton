import type { AgentPreset } from '../../shared/types';
import { makeTaskTool, askUserTool, updatePlanTool } from './meta';
import { makeOrchestrateTool, makeHandoffTool } from './orchestrate';
import type { ToolDef } from './types';

export function builtinTools(agents: AgentPreset[], maxParallel: number): ToolDef[] {
  return [
    updatePlanTool,
    makeTaskTool(agents, maxParallel),
    makeOrchestrateTool(agents, maxParallel),
    makeHandoffTool(agents),
    askUserTool,
  ];
}

export { makeTaskTool, askUserTool, updatePlanTool } from './meta';
export { makeOrchestrateTool, makeHandoffTool } from './orchestrate';
