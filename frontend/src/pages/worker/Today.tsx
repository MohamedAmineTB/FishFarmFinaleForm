// Worker "Today" (screen 30): shift progress, water alerts, my tasks, basin cards.
import { useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import { useApi, useLive } from '../../api/realtime';
import { useSession } from '../../api/session';
import type { Alert, Basin, Task } from '../../api/types';
import { useTitle } from '../../App';
import { useAssistant } from '../../assistant/context';
import { BasinCard } from '../../components/BasinCard';
import { HomeHero, Ticket, Tickets, Words, useEnter } from '../../components/Home';
import { Icon } from '../../components/Icons';
import { sevClass, useToast } from '../../components/ui';
import { fmt, greeting, hhmm, shiftInfo, today } from '../../lib/format';
import { navItems } from '../../lib/nav';
import { LoadError } from '../owner/Overview';

export interface TodayData {
  healthy: number;
  basin_count: number;
  alerts: Alert[];
  high: number;
  hero_text?: string;
  tasks?: Task[];
  overnight_low?: { value: number; time: string; basin: string } | null;
  probes?: { total: number; bad: { code: string; basin: string; health: string }[] };
  open_tasks?: Task[];
  last_calibration?: string | null;
  basins?: Basin[];
}

export function TaskCheck({ t, onChange }: { t: Task; onChange: () => void }) {
  const toast = useToast();
  const done = t.status === 'fixed';
  return (
    <label className={`task${done ? ' done' : ''}`}>
      <input
        type="checkbox"
        checked={done}
        onChange={async (e) => {
          const on = e.target.checked;
          await api(`/api/tasks/${t.id}`, { method: 'PATCH', body: { status: on ? 'fixed' : 'pending' } });
          if (on)
            toast(
              <>
                <b>Done</b> · {t.title}
              </>,
            );
          onChange();
        }}
      />
      <span>
        <span className="t">{t.title}</span>
        <span className="mini">due {t.due}</span>
      </span>
    </label>
  );
}

export default function WorkerToday() {
  useTitle('Today');
  const { me } = useSession();
  const { live } = useLive();
  const ai = useAssistant();
  const nav = useNavigate();
  const { data, error, reload } = useApi<TodayData>('/api/today', ['alert', 'task', 'farm']);
  useEnter(!!data, 'today');
  if (!data) return <LoadError error={error} />;
  const items = navItems(me!.role, me!.permissions);
  const si = shiftInfo(me!.shift);
  const first = me!.user.name.split(' ')[0];
  const tasks = data.tasks ?? [];
  const openTasks = tasks.filter((t) => t.status !== 'fixed');
  const basins = live?.basins ?? data.basins ?? [];
  const healthy = live ? live.basins.filter((b) => b.status === 'healthy').length : data.healthy;
  const low = data.overnight_low;
  return (
    <>
      <HomeHero
        eyebrow={`${today()} · shift ${si ? si.s + '–' + si.e : ''}`}
        title={
          <>
            <Words text={`${greeting()}, ${first}.`} />
            <br />
            {si?.on ? (
              <>
                <Words text={`${Math.floor(si.left!)} h ${Math.round((si.left! % 1) * 60)} min left on `} />
                <em>
                  <Words text="your shift." />
                </em>
              </>
            ) : (
              <>
                <Words text="You're " />
                <em>
                  <Words text="off shift" />
                </em>
                <Words text=" right now." />
              </>
            )}
          </>
        }
        text={data.hero_text}
        ctas={
          <>
            <button className="btn" onClick={() => ai.ask('What should I do first on this shift?')}>
              <Icon name="chat" size={15} />
              What should I do first?
            </button>
            {items.some((n) => n.key === 'shift') && (
              <button className="btn ghost" onClick={() => nav('/worker/report')}>
                Write shift report
              </button>
            )}
          </>
        }
        progress={si?.on ? si.pct : null}
      />
      <Tickets>
        <Ticket label="Water alerts" value={data.alerts.length} note={`${data.high} high severity`} alert />
        <Ticket label="My open tasks" value={openTasks.length} note="tick them off below" />
        <Ticket
          label="Healthy basins"
          value={
            <>
              {healthy}
              <sup>/{data.basin_count}</sup>
            </>
          }
          note="live status"
        />
        <Ticket
          label="Overnight O₂ low"
          value={
            <>
              {fmt(low?.value, 1)}
              <sup>mg/L</sup>
            </>
          }
          note={low ? `${low.basin} at ${hhmm(low.time)}` : 'no data yet'}
        />
      </Tickets>
      <div className="grid g2">
        <div className="tile">
          <div className="section-title">
            <h3>My tasks</h3>
            <span className="mini">{tasks.length} assigned</span>
          </div>
          {tasks.length ? tasks.map((t) => <TaskCheck key={t.id} t={t} onChange={reload} />) : <p className="mini">No tasks assigned to you.</p>}
        </div>
        <div className="tile">
          <div className="section-title">
            <h3>Needs attention</h3>
            {items.some((n) => n.key === 'alerts') && (
              <button className="small-btn" onClick={() => nav('/worker/alerts')}>
                All alerts
              </button>
            )}
          </div>
          <div className="blist">
            {data.alerts.length ? (
              data.alerts.slice(0, 4).map((a) => (
                <div className="brow" style={{ cursor: 'default' }} key={a.id}>
                  <span className="sdot" style={{ background: a.severity === 'high' || a.severity === 'critical' ? 'var(--crit)' : 'var(--warn)' }} />
                  <span className="bn">
                    <b>{a.basin}</b>
                    <span>{a.title}</span>
                  </span>
                  <span />
                  <span className={`badge ${sevClass(a.severity)}`}>{a.severity}</span>
                </div>
              ))
            ) : (
              <p className="mini">Nothing open.</p>
            )}
          </div>
        </div>
      </div>
      {me!.permissions.basins && (
        <div className="grid g2">
          {basins.map((b) => (
            <BasinCard b={b} key={b.id} />
          ))}
        </div>
      )}
    </>
  );
}
