// Basin detail (screens 12, 13, 33). Owners get editable finances; the team gets the probes list.
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../../api/client';
import { useApi, useLive } from '../../api/realtime';
import { useSession } from '../../api/session';
import type { Alert, Basin, Metric } from '../../api/types';
import { useTitle } from '../../App';
import { useAssistant } from '../../assistant/context';
import { AlertList } from '../../components/AlertList';
import { Gauge, HoverChart, Tank, basinChartProps } from '../../components/Charts';
import { useEnter } from '../../components/Home';
import { Icon } from '../../components/Icons';
import { Badge, useToast } from '../../components/ui';
import { METRIC, eur, fmt, hhmm } from '../../lib/format';
import { homePath } from '../../lib/nav';
import { LoadError } from './Overview';

interface Detail extends Basin {
  overnight_low: { value: number; time: string } | null;
  prediction: {
    probability: number;
    horizon: string;
    features: Record<string, number>;
    top_features: { name: string; label: string; value: number; unit: string }[];
    model_version: string;
  } | null;
  probes: { id: string; code: string; metric: Metric; label: string; health: string; note: string }[];
  alerts: Alert[];
}

const HEALTH_BADGE: Record<string, [string, string]> = {
  ok: ['b-healthy', 'OK'],
  stuck: ['b-critical', 'Stuck'],
  drift: ['b-warning', 'Drift'],
  spiky: ['b-warning', 'Spiky'],
  offline: ['b-critical', 'Offline'],
};
export const healthBadge = (h: string) => HEALTH_BADGE[h] ?? ['b-info', h];

function GaugeTile({ b, m }: { b: Basin; m: Metric }) {
  const t = b.thr;
  const safe =
    m === 'do'
      ? `warning below ${t.do.warn} mg/L`
      : m === 'ph'
        ? `safe ${t.ph.min}–${t.ph.max}`
        : t.temp.min != null
          ? `safe ${t.temp.min}–${t.temp.max} °C`
          : 'no verified range';
  return (
    <div className="tile">
      <span className="k">{METRIC[m].label}</span>
      <div className="gauge">
        <div style={{ width: '100%', display: 'grid', justifyItems: 'center' }}>
          <Gauge b={b} m={m} />
        </div>
        <span className="gv">
          <b className={b.cls[m]}>{fmt(b.live[m], METRIC[m].dec)}</b>
          <small>{METRIC[m].unit}</small>
        </span>
        <span className="gs">
          {safe}
          {m === 'do' && (
            <>
              {' '}
              · <span>{b.sat != null ? Math.round(b.sat) : '–'}% O₂ saturation</span>
            </>
          )}
        </span>
      </div>
    </div>
  );
}

function Finances({ b, onSaved }: { b: Basin; onSaved: () => void }) {
  const toast = useToast();
  const ai = useAssistant();
  const f = b.finance!;
  const [v, setV] = useState({ fish: b.fish, feed: f.feed, maint: f.maint, ops: f.ops });
  useEffect(() => setV({ fish: b.fish, feed: f.feed, maint: f.maint, ops: f.ops }), [b.fish, f.feed, f.maint, f.ops]);
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setV({ ...v, [k]: e.target.value === '' ? ('' as any) : +e.target.value });
  const profit = f.revenue - (+v.feed || 0) - (+v.maint || 0) - (+v.ops || 0);
  return (
    <div className="tile fin">
      <div className="row">
        <h3>Finances · this quarter</h3>
        <span className="mini">Revenue {eur(f.revenue)}</span>
      </div>
      <form
        className="grid g2"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api(`/api/basins/${b.id}/finances`, {
              method: 'PUT',
              body: { fish: +v.fish || 0, feed: +v.feed || 0, maint: +v.maint || 0, ops: +v.ops || 0 },
            });
            toast(
              <>
                <b>Saved</b> · {b.name} finances updated
              </>,
            );
            onSaved();
          } catch (err) {
            toast(<>{(err as Error).message}</>);
          }
        }}
      >
        <label className="field">
          Fish count
          <input name="fish" type="number" min={0} value={v.fish} onChange={set('fish')} />
        </label>
        <label className="field">
          Feeding cost (€)
          <input name="feed" type="number" min={0} value={v.feed} onChange={set('feed')} />
        </label>
        <label className="field">
          Maintenance cost (€)
          <input name="maint" type="number" min={0} value={v.maint} onChange={set('maint')} />
        </label>
        <label className="field">
          Operational cost (€)
          <input name="ops" type="number" min={0} value={v.ops} onChange={set('ops')} />
        </label>
        <div className="field">
          Net profit
          <b className="mono" style={{ fontSize: 20, color: profit >= 0 ? 'var(--ok)' : 'var(--crit)' }} id="profitOut">
            {eur(profit)}
          </b>
        </div>
        <div style={{ display: 'flex', alignItems: 'end', gap: 8, flexWrap: 'wrap' }}>
          <button className="small-btn primary" type="submit">
            Save changes
          </button>
          <button className="small-btn" type="button" onClick={() => ai.ask(`What if I add 500 fish to ${b.name}?`)}>
            What if…
          </button>
        </div>
      </form>
    </div>
  );
}

export default function BasinDetail() {
  const { id } = useParams();
  const { me } = useSession();
  const { live } = useLive();
  const nav = useNavigate();
  const ai = useAssistant();
  const [metric, setMetric] = useState<Metric>('do');
  const { data, error, reload } = useApi<Detail>(`/api/basins/${id}`, ['alert', 'farm', 'sensor_health']);
  const series = useApi<{ times: string[]; values: number[] }>(`/api/basins/${id}/readings?metric=${metric}`, [
    'readings',
  ]);
  const own = me!.role === 'owner';
  const lb = live?.basins.find((x) => x.id === id);
  const b = data ? ({ ...data, ...(lb ?? {}) } as Detail) : null;
  useTitle(b ? `${b.name} · ${b.species_name}` : 'Basin');
  useEnter(!!b, 'basin' + id);
  if (!b) return <LoadError error={error} />;
  const low = b.overnight_low;
  const p = b.prediction;
  const risk = p?.probability ?? b.risk;
  return (
    <>
      <div className="row">
        <button
          className="small-btn"
          onClick={() =>
            nav(own ? '/owner/basins' : me!.role === 'technician' ? '/technician/basins' : homePath(me!.role))
          }
        >
          ← {own ? 'All basins' : 'Back'}
        </button>
        <div className="row">
          <span>
            <Badge st={b.status} />
          </span>
          <button className="small-btn primary" onClick={() => ai.ask(`Explain ${b.name} oxygen curve`)}>
            <Icon name="chat" size={14} />
            Explain this basin
          </button>
        </div>
      </div>
      <div className="grid g4">
        <GaugeTile b={b} m="do" />
        <GaugeTile b={b} m="temp" />
        <GaugeTile b={b} m="ph" />
        <div className="tile">
          <span className="k">Overnight oxygen low</span>
          <span className="v">
            {fmt(low?.value, 2)}
            <small>mg/L</small>
          </span>
          <span className="mini">
            {low ? `at ${hhmm(low.time)}` : 'no data yet'} · warning below {b.thr.do.warn} mg/L
          </span>
          <Tank b={b} />
          <span className="mini">
            {b.fish.toLocaleString('en-US')} fish in {b.capacity} m³
          </span>
        </div>
      </div>
      <div className="tile">
        <div className="row">
          <h3>Last 24 hours</h3>
          <div className="tabs" role="tablist" aria-label="Metric">
            {(['do', 'temp', 'ph'] as Metric[]).map((k) => (
              <button key={k} role="tab" aria-selected={k === metric} onClick={() => setMetric(k)}>
                {METRIC[k].short}
              </button>
            ))}
          </div>
        </div>
        {series.data && series.data.values.length > 1 && series.data.values[0] != null ? (
          <HoverChart props={basinChartProps(b, metric, series.data)} metric={metric} />
        ) : (
          <p className="mini">Readings appear here a few minutes after the basin starts sending data.</p>
        )}
        <span className="mini">
          Shaded area: outside the safe range for {b.species_name.toLowerCase()} ({b.thr.src}). Hover the chart to read
          any point.
        </span>
      </div>
      <div className="grid g2">
        <div className="tile">
          <div className="row">
            <h3>Low-oxygen prediction</h3>
            <span className="badge b-est">estimate · model {p?.model_version ?? 'v1'}</span>
          </div>
          <span className="mini">Chance that oxygen falls below {b.thr.do.warn} mg/L before 06:00</span>
          <span className="v">{risk != null ? Math.round(risk * 100) + '%' : '–'}</span>
          <div className="risk-meter">
            <i
              style={{
                width: `${Math.round((risk ?? 0) * 100)}%`,
                background: (risk ?? 0) > 0.5 ? 'var(--crit)' : (risk ?? 0) > 0.2 ? 'var(--warn)' : 'var(--ok)',
              }}
            />
          </div>
          <div className="feat">
            {p ? (
              p.top_features.map((f) => (
                <div key={f.name}>
                  <span>{f.label}</span>
                  <span className="mono">
                    {f.name === 'temp_now'
                      ? fmt(f.value, 1)
                      : `${f.name === 'do_decline_3h' ? fmt(f.value, 2) : Math.round(f.value)} ${f.unit}`}
                  </span>
                </div>
              ))
            ) : (
              <div>
                <span>The model needs a few hours of readings</span>
                <span className="mono">pending</span>
              </div>
            )}
          </div>
          <button
            className="small-btn"
            style={{ alignSelf: 'flex-start' }}
            onClick={() => ai.ask(`Explain the oxygen risk of ${b.name}`)}
          >
            <Icon name="chat" size={14} />
            Explain this estimate
          </button>
        </div>
        {own ? (
          <Finances b={b} onSaved={reload} />
        ) : (
          <div className="tile">
            <h3>Probes in this basin</h3>
            <div className="list">
              {b.probes.map((s) => (
                <div className="row" key={s.id} style={{ borderBottom: '1px solid var(--line)', paddingBottom: 8 }}>
                  <span>
                    <b className="mono">{s.code}</b> <span className="mini">{s.label}</span>
                  </span>
                  <span className={`badge ${healthBadge(s.health)[0]}`}>{healthBadge(s.health)[1]}</span>
                </div>
              ))}
            </div>
            {me!.permissions.reports && (
              <button
                className="small-btn"
                style={{ justifySelf: 'start' }}
                onClick={() => nav(`${homePath(me!.role)}/report`, { state: { basin: b.id } })}
              >
                Report a problem in this basin
              </button>
            )}
          </div>
        )}
      </div>
      <div className="tile">
        <h3>Alerts in {b.name}</h3>
        {b.alerts.length ? (
          <div className="list">
            <AlertList alerts={b.alerts} onChanged={reload} />
          </div>
        ) : (
          <p className="mini">No alerts in the last 24 hours.</p>
        )}
      </div>
    </>
  );
}
