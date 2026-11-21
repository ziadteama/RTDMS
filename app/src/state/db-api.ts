import { create } from 'zustand';

import type { HrPoint, Incident, Trip, TripEvent, TripEventKind, TripSummary } from '@/trips/model';

/** Storage API shared by the SQLite build (db.ts) and the web build (db.web.ts). */
export type Db = {
  startTrip(at: number, demo: boolean): number;
  saveTrip(id: number, patch: { endedAt?: number | null; score?: number | null; summary?: TripSummary }): void;
  openTrip(): Trip | null;
  listTrips(): Trip[];
  getTrip(id: number): Trip | null;
  deleteTrip(id: number): void;
  addEvent(tripId: number, t: number, kind: TripEventKind, value: string, detail?: string | null): void;
  events(tripId: number): TripEvent[];
  addHr(tripId: number, t: number, bpm: number): void;
  hr(tripId: number): HrPoint[];
  addIncident(i: Omit<Incident, 'id'>): number;
  saveIncident(id: number, patch: Partial<Omit<Incident, 'id'>>): void;
  getIncident(id: number): Incident | null;
  incidents(tripId?: number): Incident[];
  deleteDemo(): void;
  wipe(): void;
};

/** Bumped on every write so screens re-query (cheap: trips are few, queries are indexed). */
export const useDbVersion = create<{ v: number }>(() => ({ v: 0 }));
export const bump = () => useDbVersion.setState((s) => ({ v: s.v + 1 }));

/**
 * Re-run a storage query whenever the database changes. The version is passed to the query so
 * the React Compiler sees it as an input (an unused useMemo dependency gets optimized away).
 */
export function useDbQuery<T>(query: (version: number) => T): T {
  const v = useDbVersion((s) => s.v);
  return query(v);
}
