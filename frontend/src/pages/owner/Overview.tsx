// Owner overview (screens 10, 52).
import { useNavigate } from 'react-router-dom';
import { useApi, useLive } from '../../api/realtime';
import { useSession } from '../../api/session';
import type { Action, Basin } from '../../api/types';
import { useTitle } from '../../App';
import { useAssistant } from '../../assistant/context';
import { BarChart } from '../../components/Charts';
import { CountUp, HomeHero, Ticket, Tickets, Words, useEnter } from '../../components/Home';
import { Icon } from '../../components/Icons';
import { Badge } from '../../components/ui';
import { fmt, greeting, numWord, stColor, today } from '../../lib/format';
import { FirstBasin } from './AddBasin';

interface OverviewData {
  basins: Basin[];
  alerts: { open: number; sensor: number; water: number };
  finance: { revenue: number; costs: number; profit: number; margin: number; feed_share: number };
  team: { total: number; workers: number; technicians: number };
  summary: string;
  actions: Action[];
}

export function LoadError({ error }: { error: Error | null }) {
  return error ? <div className="load-err">We couldn't load this page: {error.message} Try again in a moment.</div> : null;
}

export default function Overview() {
  useTitle('Overview');
  const { me } = useSession();
  const { live } = useLive();
  const ai = useAssistant();
  const nav = useNavigate();
  const { data, error, reload } = useApi<OverviewData>('/api/overview', ['alert', 'farm', 'task', 'team', 'report']);
  useEnter(!!data, 'overview');
  if (!data) return <LoadError error={error} />;
  if (!data.basins.length) return <FirstBasin onChange={reload} />;

  // live values and statuses come from the realtime store; money and actions from the overview
  const basins = data.basins.map((b) => ({ ...b, ...(live?.basins.find((x) => x.id === b.id) ?? {}) }));
  const need = basins.filter((b) => b.status !== 'healthy').length;
  const first = me!.user.name.split(' ')[0];
  const open = live?.open_alerts ?? data.alerts.open;
  const f = data.finance;
  const doAction = (a: Action['action']) => {
    if (a.type === 'ask') ai.ask(a.q);
    else if (a.type === 'open-basin') nav(`/owner/basins/${a.id}`);
    else nav(`/owner/${a.view}`);
  };
  const fmtTeam = `${data.team.workers} worker${data.team.workers === 1 ? '' : 's'} · ${data.team.technicians} technician${data.team.technicians === 1 ? '' : 's'}`;

  return (
    <>
      <HomeHero
        eyebrow={`${today()} · ${me!.farm.name}`}
        title={
          <>
            <Words text={`${greeting()}, ${first}.`} />
            <br />
            {need ? (
              <>
                <Words text={`${need === 1 ? 'One basin needs' : numWord(need) + ' basins need'} you `} />
                <em>
                  <Words text="today." />
                </em>
              </>
            ) : (
              <>
                <Words text="Every basin is " />
                <em>
                  <Words text="calm." />
                </em>
              </>
            )}
          </>
        }
        text={data.summary}
        ctas={
          <>
            <button className="btn" onClick={() => nav('/owner/alerts')}>
              See open alerts
            </button>
            <button className="btn ghost" onClick={() => ai.ask('What needs my attention today?')}>
              <Icon name="chat" size={15} />
              Ask about today
            </button>
          </>
        }
      />
      <Tickets>
        <Ticket label="Basins" value={<CountUp value={basins.length} />} note={`${basins.filter((b) => b.status === 'healthy').length} healthy`} />
        <Ticket label="Open alerts" value={<span data-open-count>{open}</span>} note={`${data.alerts.sensor} hardware · ${data.alerts.water} water`} alert />
        <Ticket label="Profit this quarter" value={<CountUp value={f.profit} kind="eur" />} note={`${Math.round(100 * f.margin)}% margin`} />
        <Ticket label="Team" value={<CountUp value={data.team.total} />} note={fmtTeam} />
      </Tickets>
      <div className="grid g2">
        <div className="tile">
          <div className="section-title">
            <h3>Today's actions</h3>
            <span className="mini">in order</span>
          </div>
          <ol className="todo">
            {data.actions.map((a, i) => (
              <li
                key={i}
                role="button"
                tabIndex={0}
                onClick={() => doAction(a.action)}
                onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), doAction(a.action))}
              >
                <span className="n">{i + 1}</span>
                <div>
                  <b>{a.title}</b>
                  <span>{a.text}</span>
                </div>
              </li>
            ))}
          </ol>
        </div>
        <div className="tile">
          <div className="section-title">
            <h3>Basins</h3>
            <button className="small-btn" onClick={() => nav('/owner/basins')}>
              Open basins
            </button>
          </div>
          <div className="blist">
            {basins.map((b) => (
              <button className="brow" key={b.id} onClick={() => nav(`/owner/basins/${b.id}`)}>
                <span className="sdot" style={{ background: stColor(b.status) }} />
                <span className="bn">
                  <b>{b.name}</b>
                  <span>{b.species_name}</span>
                </span>
                <span className="bv mono">
                  <b className={b.cls.do}>{fmt(b.live.do, 2)}</b> <small>mg/L O₂</small>
                </span>
                <span>
                  <Badge st={b.status} />
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
      <section className="tile" style={{ gap: 14 }}>
        <div className="section-title">
          <h3>Revenue this quarter</h3>
          <button className="small-btn" onClick={() => ai.ask('How can I raise revenue?')}>
            <Icon name="chat" size={14} />
            How can I raise it?
          </button>
        </div>
        <div className="money">
          <div>
            <span className="k">Revenue</span>
            <span className="v">
              <CountUp value={f.revenue} kind="eur" />
            </span>
          </div>
          <div>
            <span className="k">Costs · feed is {Math.round(100 * f.feed_share)}%</span>
            <span className="v">
              <CountUp value={f.costs} kind="eur" />
            </span>
          </div>
          <div>
            <span className="k">Profit</span>
            <span className="v" style={{ color: 'var(--ok)' }}>
              <CountUp value={f.profit} kind="eur" />
            </span>
          </div>
        </div>
        <span className="mini">
          <span style={{ color: '#1d6f6a' }}>■</span> revenue &nbsp; <span style={{ color: '#9cc9bf' }}>■</span> costs, per basin
        </span>
        <div className="chart">
          <BarChart basins={basins.map((b) => ({ name: b.name, revenue: b.finance!.revenue, costs: b.finance!.costs }))} />
        </div>
      </section>
    </>
  );
}
