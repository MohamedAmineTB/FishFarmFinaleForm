// Technician "Today" (screen 40): probes that need attention, hardware alerts, maintenance tasks.
import { useNavigate } from 'react-router-dom';
import { useApi } from '../../api/realtime';
import { useSession } from '../../api/session';
import { useTitle } from '../../App';
import { useAssistant } from '../../assistant/context';
import { AlertList } from '../../components/AlertList';
import { HomeHero, Ticket, Tickets, Words, useEnter } from '../../components/Home';
import { Icon } from '../../components/Icons';
import { dayMonth, greeting, numWord, today } from '../../lib/format';
import { navItems } from '../../lib/nav';
import { LoadError } from '../owner/Overview';
import type { TodayData } from '../worker/Today';

export const STATUS_LABEL: Record<string, string> = { pending: 'pending', in_progress: 'in progress', fixed: 'fixed' };

export default function TechToday() {
  useTitle('Today');
  const { me } = useSession();
  const ai = useAssistant();
  const nav = useNavigate();
  const { data, error, reload } = useApi<TodayData>('/api/today', ['alert', 'task', 'sensor_health', 'farm']);
  useEnter(!!data, 'bench');
  if (!data) return <LoadError error={error} />;
  const items = navItems(me!.role, me!.permissions);
  const bad = data.probes?.bad ?? [];
  const total = data.probes?.total ?? 0;
  const tasks = data.open_tasks ?? [];
  const first = me!.user.name.split(' ')[0];
  const stuck = data.alerts.find((a) => a.kind === 'sensor');
  const q = stuck ? `Is the ${stuck.basin} alert a sensor problem?` : 'Which sensors need calibration?';
  const lc = data.last_calibration ? dayMonth(data.last_calibration).split(' ') : null;
  return (
    <>
      <HomeHero
        eyebrow={`${today()} · ${me!.farm.name} · ${total} probes`}
        title={
          <>
            <Words text={`${greeting()}, ${first}.`} />
            <br />
            {bad.length ? (
              <>
                <Words text={`${numWord(bad.length)} probe${bad.length > 1 ? 's' : ''} need `} />
                <em>
                  <Words text="your hands." />
                </em>
              </>
            ) : (
              <>
                <Words text="Every probe reads " />
                <em>
                  <Words text="normally." />
                </em>
              </>
            )}
          </>
        }
        text={bad.map((x) => `${x.code} in ${x.basin} is ${x.health}.`).join(' ') || 'Nothing to fix right now.'}
        ctas={
          <>
            <button className="btn" onClick={() => ai.ask(q)}>
              <Icon name="chat" size={15} />
              {stuck ? `Is ${stuck.basin} a sensor problem?` : 'Which sensors need calibration?'}
            </button>
            {items.some((n) => n.key === 'sensors') && (
              <button className="btn ghost" onClick={() => nav('/technician/sensors')}>
                Open sensor health
              </button>
            )}
          </>
        }
      />
      <Tickets>
        <Ticket
          label="Probes OK"
          value={
            <>
              {total - bad.length}
              <sup>/{total}</sup>
            </>
          }
          note={bad.map((x) => x.code).join(' · ') || 'all fine'}
        />
        <Ticket label="Hardware alerts" value={data.alerts.length} note="stuck, drifting or broken" alert />
        <Ticket label="Open tasks" value={tasks.length} note={`${tasks.filter((t) => t.status === 'in_progress').length} in progress`} />
        <Ticket
          label="Last calibration"
          value={
            lc ? (
              <>
                {lc[0]}
                <sup>{lc[1]}</sup>
              </>
            ) : (
              '–'
            )
          }
          note="next round in 30 days"
        />
      </Tickets>
      <div className="grid g2">
        <div className="tile">
          <div className="section-title">
            <h3>Hardware alerts</h3>
            {items.some((n) => n.key === 'alerts') && (
              <button className="small-btn" onClick={() => nav('/technician/alerts')}>
                Open queue
              </button>
            )}
          </div>
          <div className="list">
            <AlertList alerts={data.alerts} onChanged={reload} empty={<p className="mini">No hardware alerts open.</p>} />
          </div>
        </div>
        <div className="tile">
          <div className="section-title">
            <h3>Maintenance tasks</h3>
            {items.some((n) => n.key === 'maintenance') && (
              <button className="small-btn" onClick={() => nav('/technician/maintenance')}>
                Log work
              </button>
            )}
          </div>
          {tasks.length ? (
            tasks.map((t) => (
              <div className="task" key={t.id}>
                <span>
                  <span className="t">
                    <b>{t.title}</b>
                  </span>
                  <span className="mini">
                    {t.who} · due {t.due}
                  </span>
                </span>
                <span className={`badge ${t.status === 'pending' ? 'b-warning' : 'b-info'}`} style={{ marginLeft: 'auto' }}>
                  {STATUS_LABEL[t.status]}
                </span>
              </div>
            ))
          ) : (
            <p className="mini">No open tasks.</p>
          )}
        </div>
      </div>
    </>
  );
}
