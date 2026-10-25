import { expect, test } from 'vitest';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { Result } from '../../packages/shared-types/src/index.js';
import { selfTest } from '../../apps/cli/src/self-test.js';

test('CLI self-test checks the default catalog without optional native or reconstruction tools', async () => {
  const result = await selfTest(resolve('dist/apps/cli/src/index.js'));
  expect(result.ok).toBe(true);
  expect(result.tools).toHaveLength(11);
  expect(result.tools).not.toContain('noetra.investigate_native');
  expect(result.formalSolver).toBe('passed');
});

test('production CLI serves clean stdio, validates inputs, preserves memory across host reconnects', async () => {
  const project = await mkdtemp(join(tmpdir(), 'noetra-mcp-'));
  async function connect() {
    const client = new Client({ name: 'noetra-protocol-test-host', version: '1.0.0' });
    const transport = new StdioClientTransport({ command: process.execPath, args: [resolve('dist/apps/cli/src/index.js'), 'mcp', '--project', project], stderr: 'pipe' });
    transport.stderr?.on('data', () => {});
    await client.connect(transport, { timeout: 15000 }); return { client, transport };
  }
  let connection = await connect();
  let id = '';
  try {
    const catalog = await connection.client.listTools();
    expect(catalog.tools).toHaveLength(11);
    expect(catalog.tools.every(t => t.inputSchema && t.outputSchema)).toBe(true);
    const visual = Result.parse((await connection.client.callTool({ name: 'noetra.design_visual', arguments: { action: {
      kind: 'create', brief: { subject: 'Controlled car fixture', goal: 'Keep identity before detail',
        identityFeatures: [{ id: 'body', description: 'Same body outline', layer: 'silhouette', importance: 'critical', views: ['front', 'side', 'rear'], measure: { kind: 'appearance' } }],
        detailFeatures: [{ id: 'finish', description: 'Same paint finish', layer: 'materials', importance: 'important', views: ['front', 'side', 'rear'], measure: { kind: 'appearance' } }]
      }
    } } })).structuredContent);
    expect(visual.ok).toBe(true);
    expect((visual.data.gate as { readyFor3dBrief: boolean }).readyFor3dBrief).toBe(false);
    const invalid = await connection.client.callTool({ name: 'noetra.analyze_problem', arguments: { text: '' } });
    expect(invalid.isError).toBe(true);
    const created = Result.parse((await connection.client.callTool({ name: 'noetra.analyze_problem', arguments: { text: 'Remember this controlled test problem.' } })).structuredContent);
    expect(created.ok).toBe(true); id = (created.data.record as { id: string }).id;
    const proof = Result.parse((await connection.client.callTool({ name: 'noetra.verify_claim', arguments: {
      premises: [{ id: 'p', terms: [{ variable: 'x', coefficient: 1 }], relation: 'ge', value: 2 }],
      claim: { id: 'c', terms: [{ variable: 'x', coefficient: 1 }], relation: 'ge', value: 1 }
    } }, { timeout: 15000 })).structuredContent);
    expect(proof.status).toBe('VERIFIED');
  } finally { await connection.client.close(); await connection.transport.close(); }
  connection = await connect();
  try {
    const report = Result.parse((await connection.client.callTool({ name: 'noetra.get_reasoning_report', arguments: { id } })).structuredContent);
    expect(report.ok).toBe(true); expect(report.data.records).toHaveLength(1);
  } finally { await connection.client.close(); await connection.transport.close(); }
});
