import { DatabaseSync } from 'node:sqlite';
import { mkdirSync, chmodSync } from 'node:fs';
import { dirname } from 'node:path';
import { randomUUID } from 'node:crypto';
import { fail } from '../../shared-types/src/index.js';

export interface RecordEntry {
  project: string; id: string; kind: string; revision: number;
  createdAt: string; expiresAt: string | null; value: unknown;
}
interface Row {
  project: string; id: string; kind: string; revision: number;
  created_at: string; expires_at: string | null; payload: string;
}
export class Memory {
  private readonly db: DatabaseSync;
  constructor(path: string, readonly project: string) {
    if (!project || project.length > 200) fail('INVALID_PROJECT', 'A bounded project identifier is required.');
    if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
    this.db = new DatabaseSync(path, { allowExtension: false, enableForeignKeyConstraints: true });
    this.db.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA secure_delete=ON;');
    this.db.exec(`CREATE TABLE IF NOT EXISTS records (
      project TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL,
      revision INTEGER NOT NULL, created_at TEXT NOT NULL,
      expires_at TEXT, payload TEXT NOT NULL,
      PRIMARY KEY(project,id,revision)
    ) STRICT; CREATE INDEX IF NOT EXISTS records_by_project ON records(project,kind,created_at);`);
    if (path !== ':memory:' && process.platform !== 'win32') chmodSync(path, 0o600);
  }
  put(kind: string, value: unknown, options: { id?: string; expiresAt?: string; expectedRevision?: number } = {}): RecordEntry {
    const payload = JSON.stringify(value);
    if (payload === undefined || Buffer.byteLength(payload) > 1048576) fail('RECORD_LIMIT', 'Records are limited to 1 MiB.');
    const id = options.id ?? randomUUID();
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const old = this.db.prepare('SELECT MAX(revision) AS revision FROM records WHERE project=? AND id=?').get(this.project, id) as { revision: number | null };
      const previous = old.revision ?? 0;
      if (options.expectedRevision !== undefined && previous !== options.expectedRevision) fail('REVISION_CONFLICT', 'Reload the latest revision before updating.');
      const existing = this.db.prepare('SELECT kind FROM records WHERE project=? AND id=? LIMIT 1').get(this.project, id) as { kind: string } | undefined;
      if (existing && existing.kind !== kind) fail('KIND_CONFLICT', 'A record identifier cannot change kind.');
      const count = this.db.prepare('SELECT COUNT(*) AS count FROM records WHERE project=?').get(this.project) as { count: number };
      if (count.count >= 100000) fail('MEMORY_LIMIT', 'Project memory has reached its 100,000 revision limit. Export or delete explicitly.');
      const revision = previous + 1, createdAt = new Date().toISOString();
      this.db.prepare('INSERT INTO records VALUES(?,?,?,?,?,?,?)').run(this.project, id, kind, revision, createdAt, options.expiresAt ?? null, payload);
      this.db.exec('COMMIT');
      return { project: this.project, id, kind, revision, createdAt, expiresAt: options.expiresAt ?? null, value: JSON.parse(payload) as unknown };
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }
  get(id: string): RecordEntry | undefined {
    const row = this.db.prepare('SELECT * FROM records WHERE project=? AND id=? ORDER BY revision DESC LIMIT 1').get(this.project, id) as Row | undefined;
    if (!row || (row.expires_at !== null && row.expires_at <= new Date().toISOString())) return undefined;
    return this.decode(row);
  }
  history(id: string): RecordEntry[] {
    return (this.db.prepare('SELECT * FROM records WHERE project=? AND id=? AND (expires_at IS NULL OR expires_at>?) ORDER BY revision').all(this.project, id, new Date().toISOString()) as unknown as Row[]).map(row => this.decode(row));
  }
  list(limit = 100): RecordEntry[] {
    const safe = Math.max(1, Math.min(500, Math.trunc(limit)));
    return (this.db.prepare(`SELECT r.* FROM records r WHERE project=? AND revision=(SELECT MAX(revision) FROM records s WHERE s.project=r.project AND s.id=r.id)
      AND (expires_at IS NULL OR expires_at>?) ORDER BY created_at DESC LIMIT ?`).all(this.project, new Date().toISOString(), safe) as unknown as Row[]).map(row => this.decode(row));
  }
  export(): RecordEntry[] {
    return (this.db.prepare('SELECT * FROM records WHERE project=? AND (expires_at IS NULL OR expires_at>?) ORDER BY created_at,id,revision').all(this.project, new Date().toISOString()) as unknown as Row[]).map(row => this.decode(row));
  }
  purgeExpired(): number {
    // Expiring the latest revision must not resurrect an older revision of the same record.
    const now = new Date().toISOString();
    return Number(this.db.prepare(`DELETE FROM records WHERE project=? AND (
      (expires_at IS NOT NULL AND expires_at<=?) OR id IN (
        SELECT r.id FROM records r WHERE r.project=? AND r.expires_at IS NOT NULL AND r.expires_at<=?
        AND r.revision=(SELECT MAX(s.revision) FROM records s WHERE s.project=r.project AND s.id=r.id)
      ))`).run(this.project, now, this.project, now).changes);
  }
  deleteProject(confirmation: string): number {
    if (confirmation !== this.project) fail('CONFIRMATION_REQUIRED', 'Confirm the exact project identifier.');
    return Number(this.db.prepare('DELETE FROM records WHERE project=?').run(this.project).changes);
  }
  close(): void { this.db.close(); }
  private decode(row: Row): RecordEntry {
    return { project: row.project, id: row.id, kind: row.kind, revision: row.revision, createdAt: row.created_at, expiresAt: row.expires_at, value: JSON.parse(row.payload) as unknown };
  }
}
