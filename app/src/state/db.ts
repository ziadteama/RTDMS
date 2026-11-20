import { openDatabaseSync } from 'expo-sqlite';

import { EMPTY_SUMMARY, type Incident, type Trip, type TripSummary } from '@/trips/model';

import { bump, type Db } from './db-api';

export { useDbQuery, useDbVersion } from './db-api';

const sql = openDatabaseSync('sahi.db');
sql.execSync(`
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS trips (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at INTEGER NOT NULL,
  ended_at INTEGER,
  demo INTEGER NOT NULL DEFAULT 0,
  score REAL,
  summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  t INTEGER NOT NULL,
  kind TEXT NOT NULL,
  value TEXT NOT NULL,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS events_trip ON events(trip_id, t);
CREATE TABLE IF NOT EXISTS hr (
  trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  t INTEGER NOT NULL,
  bpm REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS hr_trip ON hr(trip_id, t);
CREATE TABLE IF NOT EXISTS incidents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trip_id INTEGER,
  t INTEGER NOT NULL,
  data TEXT NOT NULL
);
PRAGMA foreign_keys = ON;
`);

type TripRow = { id: number; started_at: number; ended_at: number | null; demo: number; score: number | null; summary: string };
const toTrip = (r: TripRow): Trip => ({
  id: r.id,
  startedAt: r.started_at,
  endedAt: r.ended_at,
  demo: r.demo === 1,
  score: r.score,
  summary: { ...EMPTY_SUMMARY, ...(JSON.parse(r.summary) as TripSummary) },
});
type IncRow = { id: number; trip_id: number | null; t: number; data: string };
const toIncident = (r: IncRow): Incident => ({ ...(JSON.parse(r.data) as Omit<Incident, 'id'>), id: r.id });

export const db: Db = {
  startTrip(at, demo) {
    const r = sql.runSync('INSERT INTO trips (started_at, demo, summary) VALUES (?, ?, ?)', at, demo ? 1 : 0, JSON.stringify(EMPTY_SUMMARY));
    bump();
    return r.lastInsertRowId;
  },
  saveTrip(id, p) {
    if (p.endedAt !== undefined) sql.runSync('UPDATE trips SET ended_at = ? WHERE id = ?', p.endedAt, id);
    if (p.score !== undefined) sql.runSync('UPDATE trips SET score = ? WHERE id = ?', p.score, id);
    if (p.summary) sql.runSync('UPDATE trips SET summary = ? WHERE id = ?', JSON.stringify(p.summary), id);
    bump();
  },
  openTrip() {
    const r = sql.getFirstSync<TripRow>('SELECT * FROM trips WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1');
    return r ? toTrip(r) : null;
  },
  listTrips: () => sql.getAllSync<TripRow>('SELECT * FROM trips ORDER BY started_at DESC').map(toTrip),
  getTrip(id) {
    const r = sql.getFirstSync<TripRow>('SELECT * FROM trips WHERE id = ?', id);
    return r ? toTrip(r) : null;
  },
  deleteTrip(id) {
    sql.runSync('DELETE FROM trips WHERE id = ?', id);
    bump();
  },
  addEvent(tripId, t, kind, value, detail = null) {
    sql.runSync('INSERT INTO events (trip_id, t, kind, value, detail) VALUES (?, ?, ?, ?, ?)', tripId, t, kind, value, detail);
    bump();
  },
  events: (tripId) =>
    sql
      .getAllSync<{ id: number; trip_id: number; t: number; kind: string; value: string; detail: string | null }>(
        'SELECT * FROM events WHERE trip_id = ? ORDER BY t',
        tripId,
      )
      .map((r) => ({ id: r.id, tripId: r.trip_id, t: r.t, kind: r.kind as never, value: r.value, detail: r.detail })),
  addHr(tripId, t, bpm) {
    sql.runSync('INSERT INTO hr (trip_id, t, bpm) VALUES (?, ?, ?)', tripId, t, bpm);
  },
  hr: (tripId) => sql.getAllSync<{ t: number; bpm: number }>('SELECT t, bpm FROM hr WHERE trip_id = ? ORDER BY t', tripId),
  addIncident(i) {
    const r = sql.runSync('INSERT INTO incidents (trip_id, t, data) VALUES (?, ?, ?)', i.tripId, i.t, JSON.stringify(i));
    bump();
    return r.lastInsertRowId;
  },
  saveIncident(id, patch) {
    const cur = sql.getFirstSync<IncRow>('SELECT * FROM incidents WHERE id = ?', id);
    if (!cur) return;
    const next = { ...toIncident(cur), ...patch };
    const { id: _id, ...data } = next;
    sql.runSync('UPDATE incidents SET data = ? WHERE id = ?', JSON.stringify(data), id);
    bump();
  },
  getIncident(id) {
    const r = sql.getFirstSync<IncRow>('SELECT * FROM incidents WHERE id = ?', id);
    return r ? toIncident(r) : null;
  },
  incidents: (tripId) =>
    (tripId === undefined
      ? sql.getAllSync<IncRow>('SELECT * FROM incidents ORDER BY t DESC')
      : sql.getAllSync<IncRow>('SELECT * FROM incidents WHERE trip_id = ? ORDER BY t DESC', tripId)
    ).map(toIncident),
  deleteDemo() {
    sql.execSync('DELETE FROM incidents WHERE trip_id IN (SELECT id FROM trips WHERE demo = 1); DELETE FROM trips WHERE demo = 1;');
    bump();
  },
  wipe() {
    sql.execSync('DELETE FROM events; DELETE FROM hr; DELETE FROM incidents; DELETE FROM trips;');
    bump();
  },
};
