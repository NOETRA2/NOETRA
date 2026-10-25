import { constants } from 'node:fs';
import { lstat, open, realpath } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, extname, isAbsolute, parse, relative, resolve, sep } from 'node:path';
import { homedir } from 'node:os';
import { fail } from '../../shared-types/src/index.js';

const MAX_BYTES = 24 * 1024 * 1024;
const crcTable = Array.from({ length: 256 }, (_, value) => {
  let crc = value;
  for (let bit = 0; bit < 8; bit++) crc = (crc & 1) ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
  return crc >>> 0;
});
export function pngCrc(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = (crc >>> 8) ^ crcTable[(crc ^ byte) & 255]!;
  return (crc ^ 0xffffffff) >>> 0;
}
/** PNG container checks only. This does not decode pixels or judge image quality. */
export function inspectPng(bytes: Buffer) {
  if (bytes.length < 57 || bytes.length > MAX_BYTES || !bytes.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) fail('INVALID_PNG', 'Expected a bounded PNG image, not arbitrary file content.');
  let offset = 8, width = 0, height = 0, idat = false, ended = false, chunks = 0;
  while (offset + 12 <= bytes.length) {
    if (++chunks > 4096) fail('IMAGE_LIMIT', 'PNG exceeds the chunk-count limit.');
    const length = bytes.readUInt32BE(offset);
    const end = offset + 12 + length;
    if (length > MAX_BYTES || end > bytes.length) fail('INVALID_PNG', 'PNG chunk exceeds its file boundary.');
    const type = bytes.toString('ascii', offset + 4, offset + 8);
    if (!/^[A-Za-z]{4}$/.test(type) || pngCrc(bytes.subarray(offset + 4, end - 4)) !== bytes.readUInt32BE(end - 4)) fail('INVALID_PNG', 'PNG chunk framing/checksum is invalid.');
    if (chunks === 1 && (type !== 'IHDR' || length !== 13)) fail('INVALID_PNG', 'PNG must start with a 13-byte IHDR.');
    if (type === 'IHDR') {
      if (chunks !== 1) fail('INVALID_PNG', 'Duplicate PNG image header.');
      width = bytes.readUInt32BE(offset + 8); height = bytes.readUInt32BE(offset + 12);
      const bitDepth = bytes[offset + 16]!, colorType = bytes[offset + 17]!;
      const allowed: Record<number, number[]> = { 0: [1,2,4,8,16], 2: [8,16], 3: [1,2,4,8], 4: [8,16], 6: [8,16] };
      if (!allowed[colorType]?.includes(bitDepth) || bytes[offset + 18] !== 0 || bytes[offset + 19] !== 0 || ![0,1].includes(bytes[offset + 20]!)) fail('INVALID_PNG', 'PNG header uses unsupported/invalid parameters.');
      if (!width || !height || width > 8192 || height > 8192 || width * height > 24000000) fail('IMAGE_LIMIT', 'Image exceeds the 8192-edge / 24-megapixel limit.');
    }
    if (['acTL','fcTL','fdAT'].includes(type)) fail('UNSUPPORTED_IMAGE', 'Animated images need an explicit frame workflow; use a still PNG.');
    if (type === 'IDAT' && length > 0) idat = true;
    if (type === 'IEND') {
      if (length !== 0 || !idat || end !== bytes.length) fail('INVALID_PNG', 'Invalid PNG end or trailing data.');
      ended = true; break;
    }
    offset = end;
  }
  if (!ended) fail('INVALID_PNG', 'Incomplete PNG; image data and IEND are required.');
  return { width, height, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') };
}
function contained(root: string, target: string): boolean {
  const rel = relative(root, target);
  return rel !== '' && !isAbsolute(rel) && rel !== '..' && !rel.startsWith('..' + sep);
}
export async function imageMetadata(projectRoot: string, path: string, signal?: AbortSignal) {
  signal?.throwIfAborted();
  if (!isAbsolute(path) || extname(path).toLowerCase() !== '.png') fail('UNSUPPORTED_IMAGE', 'Provide an explicit absolute path to a still PNG inside the active project.');
  const declaredRoot = resolve(projectRoot), root = await realpath(declaredRoot);
  const home = await realpath(homedir()).catch(() => resolve(homedir()));
  if (root.toLowerCase() === home.toLowerCase() || root === parse(root).root) fail('VISUAL_SCOPE_TOO_BROAD', 'Use a dedicated visual project, not a home/drive root.');
  const requested = resolve(path);
  // The explicitly selected project may itself use an OS alias (/var on macOS,
  // an 8.3 path or a junction on Windows). Rebase only its in-project suffix;
  // child symlinks still undergo the full lstat walk below before being opened.
  const lexical = contained(root, requested) ? requested
    : contained(declaredRoot, requested) ? resolve(root, relative(declaredRoot, requested))
    : fail('IMAGE_OUTSIDE_PROJECT', 'Visual assets must stay inside the active project.');
  let parent = lexical;
  while (relative(root, parent) !== '') {
    if ((await lstat(parent)).isSymbolicLink()) fail('IMAGE_SYMLINK', 'Symlink/junction image paths are not accepted.');
    const next = dirname(parent);
    if (next === parent) fail('IMAGE_OUTSIDE_PROJECT', 'Image path is outside the project.');
    parent = next;
  }
  const canonical = await realpath(lexical);
  if (!contained(root, canonical)) fail('IMAGE_OUTSIDE_PROJECT', 'Image resolves outside the active project.');
  const handle = await open(canonical, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
  try {
    const before = await handle.stat();
    if (!before.isFile() || before.size > MAX_BYTES) fail('IMAGE_LIMIT', 'Asset must be a regular file no larger than 24 MiB.');
    const bytes = await handle.readFile({ signal });
    const after = await handle.stat();
    if (before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ino !== after.ino) fail('ASSET_CHANGED', 'Asset changed while reading. Register an immutable copy.');
    return { path: canonical, ...inspectPng(bytes) };
  } finally { await handle.close(); }
}
