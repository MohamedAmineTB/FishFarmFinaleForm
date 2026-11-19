// Formatting helpers ported from the prototype. Times are stored in UTC by the server and
// shown in the farm's local time zone.

let farmTz = 'Europe/Paris';
export const setFarmTz = (tz: string) => {
  farmTz = tz || 'Europe/Paris';
};
export const getFarmTz = () => farmTz;

export const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
export const fmt = (v: number | null | undefined, d: number) => (v == null || Number.isNaN(v) ? '–' : Number(v).toFixed(d));
export const eur = (n: number) => '€' + Math.round(n).toLocaleString('en-US');
export const initials = (n: string) =>
  n
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

const toDate = (t: string | number | Date) => (t instanceof Date ? t : new Date(t));

export const hhmm = (t: string | number | Date) =>
  toDate(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: farmTz });
export const clock = (t: Date = new Date()) => t.toLocaleTimeString('en-GB', { timeZone: farmTz });
export const fmtDate = (t: string | number | Date) =>
  toDate(t).toLocaleString('en-GB', { weekday: 'short', hour: '2-digit', minute: '2-digit', timeZone: farmTz });
export const fullDate = (t: string | number | Date) => toDate(t).toLocaleString('en-GB', { timeZone: farmTz });
export const dayMonth = (t: string | number | Date) =>
  toDate(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: farmTz });
export const today = () =>
  new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', timeZone: farmTz });

/** Local hour of the farm as a float (e.g. 10.5 for 10:30). */
export const farmHour = (t: Date = new Date()) => {
  const p = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: farmTz })
    .formatToParts(t)
    .reduce<Record<string, string>>((a, x) => ((a[x.type] = x.value), a), {});
  return Number(p.hour) + Number(p.minute) / 60;
};

export const greeting = () => {
  const h = farmHour();
  return h < 5 ? 'Good night' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
};
export const numWord = (n: number) =>
  ['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten'][n] || String(n);

export const METRIC = {
  do: { label: 'Dissolved oxygen', short: 'Oxygen', unit: 'mg/L', dec: 2 },
  temp: { label: 'Water temperature', short: 'Temp', unit: '°C', dec: 1 },
  ph: { label: 'pH', short: 'pH', unit: '', dec: 2 },
} as const;

export const ROLE_LABEL = { owner: 'Owner', worker: 'Worker', technician: 'Technician' } as const;

export const stColor = (st: string) => (st === 'critical' ? 'var(--crit)' : st === 'warning' ? 'var(--warn)' : 'var(--ok)');
export const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

export function shiftInfo(shift: { start: string; end: string } | null) {
  if (!shift) return null;
  const toH = (x: string) => {
    const [h, m] = x.split(':').map(Number);
    return h + m / 60;
  };
  const s = toH(shift.start);
  const e = toH(shift.end);
  const n = farmHour();
  const len = (e - s + 24) % 24 || 24;
  const el = (n - s + 24) % 24;
  const on = el <= len;
  return { s: shift.start, e: shift.end, on, pct: on ? Math.round((100 * el) / len) : 0, left: on ? len - el : null };
}
