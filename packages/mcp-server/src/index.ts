import { McpServer } from '@modelcontextprotocol/server';
import type { ServerContext } from '@modelcontextprotocol/server';
import { NoetraEngine } from '../../core/src/index.js';
import { schemas, descriptions } from '../../core/src/schemas.js';
import type { ToolName } from '../../core/src/schemas.js';
import { Result, VERSION } from '../../shared-types/src/index.js';
import { isReconstructionTool } from '../../reconstruction/src/index.js';

export function createServer(engine: NoetraEngine): McpServer {
  const server = new McpServer({ name: 'noetra', version: VERSION }, { maxToolInputElements: 20000 });
  for (const name of Object.keys(schemas) as ToolName[]) {
    if(isReconstructionTool(name) && !engine.reconstruction.enabled) continue;
    if(name==='noetra.investigate_native'&&!engine.rea.nativeEnabled)continue;
    server.registerTool(name, {
      description: descriptions[name], inputSchema: schemas[name], outputSchema: Result,
      annotations: { readOnlyHint: name === 'noetra.get_reasoning_report', destructiveHint: false,
        idempotentHint: name === 'noetra.get_reasoning_report', openWorldHint: name === 'noetra.investigate_software' }
    }, async (input: unknown, context: ServerContext) => {
      const output = await engine.call(name, input, context.mcpReq.signal);
      return { content: [{ type: 'text' as const, text: JSON.stringify(output) }], structuredContent: output, isError: !output.ok };
    });
  }
  return server;
}
