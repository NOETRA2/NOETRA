import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { VERSION, fail, Result } from '../../../packages/shared-types/src/index.js';
import { schemas } from '../../../packages/core/src/schemas.js';
import { isReconstructionTool } from '../../../packages/reconstruction/src/index.js';

export async function selfTest(cli: string) {
  const project = await mkdtemp(join(tmpdir(), 'noetra-self-test-'));
  const client = new Client({ name: 'noetra-self-test', version: VERSION });
  const transport = new StdioClientTransport({ command: process.execPath, args: [cli, 'mcp', '--project', project], stderr: 'pipe', maxBufferSize: 1048576 });
  transport.stderr?.on('data', () => {});
  try {
    await client.connect(transport, { timeout: 15000 });
    const tools = await client.listTools();
    const expected = Object.keys(schemas).filter(name=>!isReconstructionTool(name) && name !== 'noetra.investigate_native').sort();
    if (JSON.stringify(tools.tools.map(t => t.name).sort()) !== JSON.stringify(expected)) fail('SELF_TEST', 'NOETRA tool catalog does not match its declared operations.');
    const premise = { id: 'lower', terms: [{ variable: 'x', coefficient: 1 }], relation: 'ge', value: 2 };
    const claim = { ...premise, id: 'positive', value: 1 };
    const result = await client.callTool({ name: 'noetra.verify_claim', arguments: { premises: [premise], claim } }, { timeout: 15000 });
    if (result.isError || Result.parse(result.structuredContent).status !== 'VERIFIED') fail('SELF_TEST', 'Formal entailment MCP test failed.');
    return { ok: true, protocolConnection: true, tools: tools.tools.map(t => t.name), formalSolver: 'passed', project,
      limitation: 'Official SDK protocol client smoke test, not proof of a connected Codex/Claude/Cursor UI or model-quality improvement.' };
  } finally { await client.close().catch(() => {}); await transport.close().catch(() => {}); }
}
