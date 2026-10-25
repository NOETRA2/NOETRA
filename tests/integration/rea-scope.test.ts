import { expect, test } from 'vitest';
import { ReaBridge, validateRoot } from '../../packages/integrations/rea/src/index.js';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { join, parse, resolve } from 'node:path';
import { tmpdir } from 'node:os';

test('REA scope is enforced before launching any integration', async () => {
  const allowed = resolve('examples/software-investigation/electron-sample');
  const bridge = new ReaBridge({ enabled: true, packageDirectory: 'does-not-exist-and-must-not-be-launched', allowedRoots: [allowed], version: '6.7.0' }, resolve('.noetra/test-rea'));
  await expect(bridge.investigate({ target: process.cwd(), scope: 'test rejection', authorization: 'scope fixture only', sourcePaths: ['package.json'] })).rejects.toMatchObject({ code: 'TARGET_NOT_AUTHORIZED' });
  await expect(bridge.investigate({ target: allowed, scope: 'test rejection', authorization: 'scope fixture only', sourcePaths: ['../outside.js'] })).rejects.toMatchObject({ code: 'INVALID_SOURCE_PATH' });
  await expect(validateRoot(parse(allowed).root)).rejects.toMatchObject({ code: 'SCOPE_TOO_BROAD' });
});
test('oversized source and missing official integration return explicit failures', async () => {
  const target = await mkdtemp(join(tmpdir(), 'noetra-rea-boundary-'));
  await writeFile(join(target, 'large.js'), 'x'.repeat(2 * 1024 * 1024 + 1));
  await writeFile(join(target, 'small.js'), '// static fixture');
  const bridge = new ReaBridge({ enabled: true, packageDirectory: 'missing-reviewed-package', allowedRoots: [target], version: '6.7.0' }, join(target, 'integration-state'));
  await expect(bridge.investigate({ target, scope: 'size budget fixture', authorization: 'fixture only', sourcePaths: ['large.js'] })).rejects.toMatchObject({ code: 'SOURCE_LIMIT' });
  await expect(bridge.investigate({ target, scope: 'missing package fixture', authorization: 'fixture only', sourcePaths: ['small.js'] })).rejects.toMatchObject({ code: 'REA_UNAVAILABLE' });
});

test('Ghidra is never claimed configured by a plain REA bridge',async()=>{
  const bridge=new ReaBridge(undefined,resolve('.noetra/test-native'));
  expect(bridge.nativeEnabled).toBe(false);
  await expect(bridge.investigateNative({target:process.execPath,scope:'fixture',authorization:'test',procedures:['entry']})).rejects.toMatchObject({code:'REA_GHIDRA_DISABLED'});
});

test('native target scope is checked before launching Ghidra or reading another file',async()=>{
  const root=await mkdtemp(join(tmpdir(),'noetra-native-scope-'));
  const bridge=new ReaBridge({enabled:true,version:'6.7.0',packageDirectory:'missing',allowedRoots:[root],ghidra:{installDirectory:root,javaHome:root}},join(root,'state'));
  expect(bridge.nativeEnabled).toBe(true);
  await expect(bridge.investigateNative({target:process.execPath,scope:'fixture',authorization:'test',procedures:['entry']})).rejects.toMatchObject({code:'TARGET_NOT_AUTHORIZED'});
  const text=join(root,'not-native.txt');await writeFile(text,'not an executable');
  await expect(bridge.investigateNative({target:text,scope:'fixture',authorization:'test',procedures:['entry']})).rejects.toMatchObject({code:'NATIVE_TARGET_LIMIT'});
});
