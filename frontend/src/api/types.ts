export type Role = 'owner' | 'worker' | 'technician';
export type Metric = 'do' | 'temp' | 'ph';
export type Status = 'healthy' | 'warning' | 'critical' | 'inactive';
export type Perms = Partial<Record<'reports' | 'alerts' | 'basins' | 'sensors' | 'maintenance', boolean>>;

export interface Me {
  user: { id: string; name: string; email: string };
  role: Role;
  permissions: Perms;
  shift: { start: string; end: string } | null;
  farm: { name: string; company: string; country: string; timezone: string };
  assistant: { provider: string; demo_mode: boolean };
}

export interface Thr {
  species: string;
  name: string;
  do: { warn: number | null; crit: number | null; emergency: number | null };
  temp: { min: number | null; max: number | null };
  ph: { min: number | null; max: number | null };
  src: string;
}

export interface Basin {
  id: string;
  name: string;
  species: string;
  species_name: string;
  status: Status;
  live: Record<Metric, number | null>;
  cls: Record<Metric, string>;
  sat: number | null;
  capacity: number;
  fish: number;
  density: number;
  risk: number | null;
  thr: Thr;
  sensors: Partial<Record<Metric, { id: string; code: string; health: string }>>;
  finance?: { revenue: number; feed: number; maint: number; ops: number; costs: number; profit: number };
}

export interface Alert {
  id: string;
  basin_id: string;
  basin: string;
  species_name: string;
  metric: Metric;
  metric_label: string;
  kind: 'water' | 'sensor';
  type: string;
  title: string;
  text: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  value: number | null;
  time: string;
  resolved: boolean;
  resolved_at: string | null;
  by: string | null;
  note: string | null;
}

export interface Live {
  basins: Basin[];
  alerts: Alert[];
  open_alerts: number;
  unread_reports: number;
  simulator: { paused: boolean };
  server_time: string;
}

export interface Task {
  id: string;
  title: string;
  who: string;
  assignee_id: string | null;
  due: string;
  due_date: string | null;
  status: 'pending' | 'in_progress' | 'fixed';
  source: string;
}

export interface Report {
  id: string;
  title: string;
  body: string;
  kind: string;
  time: string;
  author: string;
  role: 'Worker' | 'Technician' | 'Owner';
  read: boolean;
}

export interface Member {
  id: string;
  name: string;
  email: string;
  role: 'worker' | 'technician';
  shift_start: string;
  shift_end: string;
  permissions: Perms;
}

export interface Action {
  time: string;
  title: string;
  text: string;
  action: { type: 'ask'; q: string } | { type: 'open-basin'; id: string } | { type: 'nav'; view: string };
}
