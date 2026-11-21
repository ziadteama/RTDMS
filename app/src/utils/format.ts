export function formatDateTime(t: number): string {
  return new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(t);
}

export function formatTime(t: number, seconds = false): string {
  return new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', second: seconds ? '2-digit' : undefined }).format(t);
}

/** Compact day/month for chart axes ("28/9"); fits eight columns on a narrow phone. */
export function formatWeek(t: number): string {
  const d = new Date(t);
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

/** "1 h 05 min" / "12 min" / "45 s". */
export function formatDuration(ms: number, u: { h: string; min: string; s: string }): string {
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s} ${u.s}`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} ${u.min}`;
  return `${Math.floor(m / 60)} ${u.h} ${String(m % 60).padStart(2, '0')} ${u.min}`;
}
