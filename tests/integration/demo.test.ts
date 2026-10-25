import { afterAll, beforeAll, expect, test } from 'vitest';
import type { Server } from 'node:http';
import { createDemoServer } from '../../dist/apps/demo/src/server.js';

let server: Server, base: string;
beforeAll(async () => {
  server = createDemoServer();
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('No test port.');
  base = `http://127.0.0.1:${address.port}`;
});
afterAll(async () => { await new Promise<void>(resolve => server.close(() => resolve())); });
const post = (body: unknown, headers = {}) => fetch(base+'/api/demo', { method:'POST', headers:{'Content-Type':'application/json', ...headers}, body:JSON.stringify(body) });

test('demo checks real entailment and returns a counterexample for a stronger claim', async () => {
  const good = await (await post({example:'logic',lowerBound:2,claimBound:1})).json();
  expect(good.result.status).toBe('VERIFIED');
  const bad = await (await post({example:'logic',lowerBound:2,claimBound:5})).json();
  expect(bad.result.status).toBe('CONTRADICTED');
  expect(bad.result.data.record.value.entailment).toBe('counterexample');
});
test('planning responds to the missing prerequisite; evidence remains an observation', async () => {
  const blocked = await (await post({example:'planning',testsPassed:false})).json();
  const ready = await (await post({example:'planning',testsPassed:true})).json();
  expect(blocked.result.status).toBe('CONTRADICTED');
  expect(ready.result.data.record.value.order).toEqual(['build','review','release']);
  const a = await (await post({example:'evidence'})).json();
  const b = await (await post({example:'evidence'})).json();
  expect(a.result.status).toBe('OBSERVED');
  expect(a.result.data.record.value.untrusted).toBe(true);
  expect(a.result.data.record.id).not.toBe(b.result.data.record.id);
});
test('public demo rejects cross-origin calls, arbitrary tool commands and oversized inputs', async () => {
  expect((await post({example:'evidence'}, {Origin:'https://other.invalid'})).status).toBe(403);
  expect((await post({example:'evidence'}, {Origin:'null'})).status).toBe(403);
  expect((await post({example:'evidence',tool:'noetra.investigate_software'})).status).toBe(400);
  expect((await post({example:'logic',lowerBound:2,claimBound:1000})).status).toBe(400);
  expect((await post({example:'evidence',padding:'x'.repeat(5000)})).status).toBe(413);
  expect((await fetch(base+'/api/demo',{method:'POST',body:'{}'})).status).toBe(415);
  expect((await fetch(base+'/../package.json')).status).toBe(404);
  expect((await fetch(base+'/constructor')).status).toBe(404);
});
test('demo serves only its UI assets and health response with a restrictive policy', async () => {
  expect((await (await fetch(base+'/health')).json()).gpuRequired).toBe(false);
  const page = await fetch(base+'/');
  expect(await page.text()).toContain('Give your agent a checkable trail');
  expect(page.headers.get('content-security-policy')).toContain("script-src 'self'");
  expect((await fetch(base+'/app.js')).status).toBe(200);
  expect((await fetch(base+'/style.css')).status).toBe(200);
});
