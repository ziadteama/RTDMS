import type { Db } from './db-api';

import { db as webDb } from './db.web';

const { db } = jest.requireActual<{ db: Db }>('./db.ts');

// Exercise the production SQL against real SQLite, including foreign keys and transactions.
jest.mock('expo-sqlite', () => {
  const { DatabaseSync } = jest.requireActual('node:sqlite');
  const sql = new DatabaseSync(':memory:');
  return { openDatabaseSync: () => ({
    execSync: (query: string) => sql.exec(query),
    runSync: (query: string, ...params: unknown[]) => {
      const result = sql.prepare(query).run(...params);
      return { ...result, lastInsertRowId: Number(result.lastInsertRowid) };
    },
    getFirstSync: (query: string, ...params: unknown[]) => sql.prepare(query).get(...params) ?? null,
    getAllSync: (query: string, ...params: unknown[]) => sql.prepare(query).all(...params),
    withTransactionSync: (run: () => void) => {
      sql.exec('BEGIN');
      try { run(); sql.exec('COMMIT'); } catch (error) { sql.exec('ROLLBACK'); throw error; }
    },
  }) };
});

test.each([['SQLite', db], ['web', webDb]] as const)('%s deletes all per-trip rows only for the selected trip', (_, store) => {
  store.wipe();
  const id = store.startTrip(1, false);
  const other = store.startTrip(2, false);
  for (const tripId of [id, other]) {
    store.addHr(tripId, 3, 70);
    store.addEvent(tripId, 3, 'sos', '1');
    store.addIncident({ tripId, t: 3, kind: 'manual', gPeak: null, lat: null, lon: null,
      piId: null, outcome: 'cancelled', checks: null, motion: [], clipPath: null, smsSent: 0, called: null });
  }
  store.deleteTrip(id);
  expect(store.getTrip(id)).toBeNull();
  expect(store.hr(id)).toEqual([]);
  expect(store.events(id)).toEqual([]);
  expect(store.incidents(id)).toEqual([]);
  expect(store.hr(other)).toHaveLength(1);
  expect(store.events(other)).toHaveLength(1);
  expect(store.incidents(other)).toHaveLength(1);
});
