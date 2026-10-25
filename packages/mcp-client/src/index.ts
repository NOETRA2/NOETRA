import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport, getDefaultEnvironment } from '@modelcontextprotocol/client/stdio';
import { VERSION } from '../../shared-types/src/index.js';

/** Only trusted local adapter configuration supplies executable/args, never public tool input. */
export async function connectLocal(command: string, args: string[], cwd: string, signal?: AbortSignal, environment: Record<string,string> = {}) {
  const client = new Client({ name: 'noetra-integration-client', version: VERSION });
  const transport = new StdioClientTransport({ command, args, cwd,
    env: { ...getDefaultEnvironment(), REA_MCP_INPUT_SCHEMA_PROFILE: 'full', ...environment },
    // REA's real 207-tool full discovery catalog is ~9.1 MB. It is never mirrored to the host.
    stderr: 'pipe', maxBufferSize: 12 * 1024 * 1024 });
  // Drain and discard stderr. Raw external logs can contain sensitive target data.
  transport.stderr?.on('data', () => {});
  try {
    await client.connect(transport, { timeout: 10000, signal });
    return { client, transport };
  } catch (error) { await client.close().catch(() => {}); await transport.close().catch(() => {}); throw error; }
}
