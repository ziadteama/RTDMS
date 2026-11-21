// Web build (screenshots / UI checks): the same API kept in memory.
import { EMPTY_SUMMARY, type HrPoint, type Incident, type Trip, type TripEvent } from '@/trips/model';

import { bump, type Db } from './db-api';

export { useDbQuery, useDbVersion } from './db-api';

let trips: Trip[] = [];
let events: TripEvent[] = [];
let hr: (HrPoint & { tripId: number })[] = [];
let incidents: Incident[] = [];
let seq = 1;

export const db: Db = {
  startTrip(at, demo) {
    const id = seq++;
    trips.push({ id, startedAt: at, endedAt: null, demo, score: null, summary: structuredClone(EMPTY_SUMMARY) });
    bump();
    return id;
  },
  saveTrip(id, p) {
    trips = trips.map((t) => (t.id === id ? { ...t, ...p } : t));
    bump();
  },
  openTrip: () => [...trips].reverse().find((t) => t.endedAt === null) ?? null,
  listTrips: () => [...trips].sort((a, b) => b.startedAt - a.startedAt),
  getTrip: (id) => trips.find((t) => t.id === id) ?? null,
  deleteTrip(id) {
    trips = trips.filter((t) => t.id !== id);
    events = events.filter((e) => e.tripId !== id);
    bump();
  },
  addEvent(tripId, t, kind, value, detail = null) {
    events.push({ id: seq++, tripId, t, kind, value, detail });
    bump();
  },
  events: (tripId) => events.filter((e) => e.tripId === tripId).sort((a, b) => a.t - b.t),
  addHr(tripId, t, bpm) {
    hr.push({ tripId, t, bpm });
  },
  hr: (tripId) => hr.filter((h) => h.tripId === tripId),
  addIncident(i) {
    const id = seq++;
    incidents.push({ ...i, id });
    bump();
    return id;
  },
  saveIncident(id, patch) {
    incidents = incidents.map((i) => (i.id === id ? { ...i, ...patch } : i));
    bump();
  },
  getIncident: (id) => incidents.find((i) => i.id === id) ?? null,
  incidents: (tripId) => incidents.filter((i) => tripId === undefined || i.tripId === tripId).sort((a, b) => b.t - a.t),
  deleteDemo() {
    const demoIds = new Set(trips.filter((t) => t.demo).map((t) => t.id));
    trips = trips.filter((t) => !t.demo);
    events = events.filter((e) => !demoIds.has(e.tripId));
    hr = hr.filter((h) => !demoIds.has(h.tripId));
    incidents = incidents.filter((i) => i.tripId === null || !demoIds.has(i.tripId));
    bump();
  },
  wipe() {
    trips = [];
    events = [];
    hr = [];
    incidents = [];
    bump();
  },
};
