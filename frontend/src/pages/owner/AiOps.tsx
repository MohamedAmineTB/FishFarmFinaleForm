// AI Ops (owner only): assistant usage, latency, cost, most-used tools and feedback over 14 days.
import { useApi } from '../../api/realtime';
import { useTitle } from '../../App';
import { LineChart } from '../../components/Charts';
import { useEnter } from '../../components/Home';
import { dayMonth, fmtDate } from '../../lib/format';
import { LoadError } from './Overview';

interface Ops {
  days: { day: string; requests: number; latency_ms: number; cost_usd: number }[];
  total: { requests: number; avg_latency_ms: number; cost_usd: number; tokens: number; errors: number; users: number };
  tools: { name: string; n: number }[];
  feedback: { up: number; down: number; up_rate: number | null };
  providers: { provider: string; model: string; requests: number; cost_usd: number }[];
  recent: { at: string; user: string; latency_ms: number; tokens: number; cost_usd: number; tools: string[]; status: string; feedback: number | null }[];
  negative_reasons: { reason: string; at: string }[];
}

function Bars({ days }: { days: Ops['days'] }) {
  const W = 640;
  const H = 200;
  const pl = 34;
  const pr = 10;
  const pt = 12;
  const pb = 26;
  const mx = Math.max(4, ...days.map((d) => d.requests));
  const y = (v: number) => pt + (H - pt - pb) * (1 - v / mx);
  const cw = (W - pl - pr) / days.length;
  return (
    <svg className="bars" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Assistant requests per day">
      {[0, 1, 2, 3, 4].map((k) => (
        <g key={k}>
          <line x1={pl} x2={W - pr} y1={y((mx * k) / 4)} y2={y((mx * k) / 4)} stroke="#e6eeeb" />
          <text x={pl - 6} y={y((mx * k) / 4) + 3.5} textAnchor="end">
            {Math.round((mx * k) / 4)}
          </text>
        </g>
      ))}
      {days.map((d, i) => (
        <g key={d.day}>
          <rect x={pl + i * cw + cw * 0.2} y={y(d.requests)} width={cw * 0.6} height={H - pb - y(d.requests)} rx="3" fill="#1d6f6a" className="grow" style={{ animationDelay: `${i * 0.03}s` }}>
            <title>
              {d.day}: {d.requests} requests
            </title>
          </rect>
          {i % 2 === 0 && (
            <text x={pl + i * cw + cw / 2} y={H - 8} textAnchor="middle">
              {dayMonth(d.day + 'T12:00:00Z')}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}

export default function AiOps() {
  useTitle('AI Ops');
  const { data, error } = useApi<Ops>('/api/ai-ops', []);
  useEnter(!!data, 'aiops');
  if (!data) return <LoadError error={error} />;
  const t = data.total;
  const lat = data.days.map((d) => d.latency_ms);
  const maxTool = Math.max(1, ...data.tools.map((x) => x.n));
  return (
    <>
      <div className="section-title">
        <p className="mini" style={{ maxWidth: '70ch' }}>
          How the farm assistant is used and how well it answers, over the last 14 days. Every request is logged with its latency, tokens, estimated cost, tools and feedback.
        </p>
      </div>
      <div className="grid g4 ops-kpis">
        <div className="tile">
          <span className="k">Requests</span>
          <span className="v">{t.requests}</span>
          <span className="mini">{t.errors} with an error</span>
        </div>
        <div className="tile">
          <span className="k">Average latency</span>
          <span className="v">
            {(t.avg_latency_ms / 1000).toFixed(1)}
            <small>s</small>
          </span>
          <span className="mini">from question to last word</span>
        </div>
        <div className="tile">
          <span className="k">Estimated cost</span>
          <span className="v">${t.cost_usd.toFixed(t.cost_usd < 1 ? 4 : 2)}</span>
          <span className="mini">{t.tokens.toLocaleString('en-US')} tokens</span>
        </div>
        <div className="tile">
          <span className="k">Thumbs up</span>
          <span className="v">{data.feedback.up_rate != null ? Math.round(data.feedback.up_rate * 100) + '%' : '–'}</span>
          <span className="mini">
            {data.feedback.up} up · {data.feedback.down} down
          </span>
        </div>
      </div>
      <div className="grid g2">
        <div className="tile">
          <h3>Requests per day</h3>
          <div className="chart">
            <Bars days={data.days} />
          </div>
        </div>
        <div className="tile">
          <h3>Latency per day</h3>
          <div className="chart">
            {lat.some((v) => v > 0) ? (
              <LineChart values={lat} min={0} max={Math.max(1000, ...lat) * 1.2} dec={0} color="#1d6f6a" h={200} label="Average latency per day (ms)" />
            ) : (
              <p className="mini">No requests yet.</p>
            )}
          </div>
          <span className="mini">milliseconds, average per day</span>
        </div>
      </div>
      <div className="grid g2">
        <div className="tile">
          <h3>Most used tools</h3>
          {data.tools.length ? (
            <div className="bar-list">
              {data.tools.map((x) => (
                <div key={x.name}>
                  <span className="mono">{x.name}</span>
                  <i style={{ width: `${Math.max(3, Math.round((100 * x.n) / maxTool))}%` }} />
                  <span className="mono">{x.n}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="mini">No tool calls yet.</p>
          )}
        </div>
        <div className="tile">
          <h3>Models</h3>
          {data.providers.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Model</th>
                    <th>Requests</th>
                    <th>Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {data.providers.map((p) => (
                    <tr key={p.provider + p.model}>
                      <td>{p.provider === 'mock' ? 'Demo mode' : p.provider}</td>
                      <td className="mono">{p.model}</td>
                      <td className="mono">{p.requests}</td>
                      <td className="mono">${p.cost_usd.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mini">No requests yet.</p>
          )}
          {data.negative_reasons.length > 0 && (
            <>
              <h3>Why answers were not useful</h3>
              <ul className="mini" style={{ paddingLeft: 18 }}>
                {data.negative_reasons.map((r) => (
                  <li key={r.at}>{r.reason}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
      <div className="tile">
        <h3>Recent requests</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Tools</th>
                <th>Latency</th>
                <th>Tokens</th>
                <th>Status</th>
                <th>Feedback</th>
              </tr>
            </thead>
            <tbody>
              {data.recent.map((r) => (
                <tr key={r.at}>
                  <td className="mono">{fmtDate(r.at)}</td>
                  <td>{r.user}</td>
                  <td className="mini mono">{r.tools.join(', ') || '–'}</td>
                  <td className="mono">{r.latency_ms} ms</td>
                  <td className="mono">{r.tokens}</td>
                  <td>
                    <span className={`badge ${r.status === 'ok' ? 'b-healthy' : 'b-critical'}`}>{r.status}</span>
                  </td>
                  <td>{r.feedback === 1 ? '👍' : r.feedback === -1 ? '👎' : '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
