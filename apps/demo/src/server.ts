import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { runDemo } from './engine.js';
import { VERSION } from '../../../packages/shared-types/src/index.js';

export function createDemoServer() {
  let active = 0;
  const server = createServer(async (req, res) => {
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'");
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('Cache-Control', 'no-store');
    const send = (status: number, value: unknown) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(value)); };
    try {
      const url = new URL(req.url ?? '/', 'http://demo.invalid');
      if (req.method === 'GET' && url.pathname === '/health') { send(200, { ok: true, version: VERSION, gpuRequired: false }); return; }
      const assets: Record<string, [string, string]> = { '/': ['index.html', 'text/html; charset=utf-8'], '/app.js': ['app.js', 'text/javascript; charset=utf-8'], '/style.css': ['style.css', 'text/css; charset=utf-8'] };
      const asset = Object.hasOwn(assets, url.pathname) ? assets[url.pathname] : undefined;
      if (req.method === 'GET' && asset) {
        const bytes = await readFile(new URL('../public/' + asset[0], import.meta.url));
        res.writeHead(200, { 'Content-Type': asset[1] }); res.end(bytes); return;
      }
      if (req.method !== 'POST' || url.pathname !== '/api/demo') { send(404, { error: 'Not found' }); return; }
      // JSON only, with no permissive CORS: cross-site forms cannot invoke work.
      if ((req.headers['content-type'] ?? '').split(';')[0] !== 'application/json') { send(415, { error: 'JSON required' }); return; }
      const origin = req.headers.origin;
      if (origin) {
        let parsed: URL;
        try { parsed = new URL(origin); } catch { send(403, { error: 'Same-origin requests only' }); return; }
        if (!['http:', 'https:'].includes(parsed.protocol) || parsed.host !== req.headers.host) { send(403, { error: 'Same-origin requests only' }); return; }
      }
      if (active >= 2) { send(429, { error: 'Demo is busy; try again shortly.' }); return; }
      active++;
      try {
        let size = 0; const chunks: Buffer[] = [];
        for await (const chunk of req) { const bytes = Buffer.from(chunk); size += bytes.length; if (size > 4096) { send(413, { error: 'Example input is too large.' }); return; } chunks.push(bytes); }
        const result = await runDemo(JSON.parse(Buffer.concat(chunks).toString('utf8')));
        send(result.result.ok ? 200 : 503, result);
      } finally { active--; }
    } catch (error) {
      if (!res.headersSent) send(error instanceof SyntaxError || (error instanceof Error && error.name === 'ZodError') ? 400 : 500, { error: 'Use the supplied example controls and try again.' });
      else res.end();
    }
  });
  server.headersTimeout = 10000; server.requestTimeout = 15000; server.keepAliveTimeout = 5000; server.maxConnections = 32;
  return server;
}

export async function startDemo(port = 7860, host = '127.0.0.1') {
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Invalid demo port.');
  const server = createDemoServer();
  await new Promise<void>((resolve, reject) => { server.once('error', reject); server.listen(port, host, resolve); });
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const server = await startDemo(Number(process.env.PORT ?? 7860), process.env.HOST ?? '127.0.0.1');
  const address = server.address();
  console.log(`NOETRA demo listening on port ${address && typeof address === 'object' ? address.port : 7860}`);
  for (const signal of ['SIGINT', 'SIGTERM'] as const) process.once(signal, () => { server.close(); });
}
