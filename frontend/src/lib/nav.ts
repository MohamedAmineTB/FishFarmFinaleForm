import type { Perms, Role } from '../api/types';

export type NavItem = { key: string; label: string; icon: string; path: string; count?: 'alerts' | 'reports' };

/** Menu per role; team members only see pages their owner switched on (Today is always there). */
export function navItems(role: Role, p: Perms): NavItem[] {
  if (role === 'owner')
    return [
      { key: 'overview', label: 'Overview', icon: 'overview', path: '/owner' },
      { key: 'basins', label: 'Basins', icon: 'basins', path: '/owner/basins' },
      { key: 'alerts', label: 'Alerts', icon: 'alerts', path: '/owner/alerts', count: 'alerts' },
      { key: 'reports', label: 'Reports', icon: 'reports', path: '/owner/reports', count: 'reports' },
      { key: 'team', label: 'Team', icon: 'team', path: '/owner/team' },
      { key: 'ai-ops', label: 'AI Ops', icon: 'ops', path: '/owner/ai-ops' },
    ];
  if (role === 'worker')
    return [
      { key: 'today', label: 'Today', icon: 'gauge', path: '/worker' },
      p.alerts && { key: 'alerts', label: 'Alerts', icon: 'alerts', path: '/worker/alerts', count: 'alerts' as const },
      p.reports && { key: 'shift', label: 'Shift report', icon: 'shift', path: '/worker/report' },
      p.sensors && { key: 'sensors', label: 'Sensor health', icon: 'sensors', path: '/worker/sensors' },
      p.maintenance && { key: 'maintenance', label: 'Maintenance', icon: 'maintenance', path: '/worker/maintenance' },
    ].filter(Boolean) as NavItem[];
  return [
    { key: 'today', label: 'Today', icon: 'gauge', path: '/technician' },
    p.alerts && { key: 'alerts', label: 'Hardware alerts', icon: 'alerts', path: '/technician/alerts', count: 'alerts' as const },
    p.sensors && { key: 'sensors', label: 'Sensor health', icon: 'sensors', path: '/technician/sensors' },
    p.maintenance && { key: 'maintenance', label: 'Maintenance', icon: 'maintenance', path: '/technician/maintenance' },
    p.basins && { key: 'basins', label: 'Basins', icon: 'basins', path: '/technician/basins' },
    p.reports && { key: 'shift', label: 'Shift report', icon: 'shift', path: '/technician/report' },
  ].filter(Boolean) as NavItem[];
}

export const homePath = (role: Role) => (role === 'owner' ? '/owner' : role === 'worker' ? '/worker' : '/technician');
export const authPath = (role: Role | string) => (role === 'owner' ? '/owner-auth' : '/worker-auth');
export const basinPath = (role: Role, id: string) => `${homePath(role)}/basins/${id}`;
