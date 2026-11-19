// Hand-drawn SVG charts ported from the prototype: lineChart, spark, barChart, gauge, tank.
import { useId, useRef, useState, type CSSProperties } from 'react';
import type { Basin, Metric } from '../api/types';
import { METRIC, clamp, eur, fmt, hhmm } from '../lib/format';
import { FishSvg } from './Icons';

export interface LineChartProps {
  values: number[];
  times?: string[];
  min: number;
  max: number;
  dec?: number;
  warn?: number | null;
  dir?: 'below' | 'above';
  color: string;
  w?: number;
  h?: number;
  label?: string;
  mark?: { i: number; label: string } | null;
}

export function LineChart(o: LineChartProps) {
  const W = o.w || 640;
  const H = o.h || 220;
  const pl = 40;
  const pr = 16;
  const pt = 16;
  const pb = 26;
  const n = o.values.length;
  const x = (i: number) => pl + ((W - pl - pr) * i) / (n - 1);
  const y = (v: number) => pt + (H - pt - pb) * (1 - (v - o.min) / (o.max - o.min));
  const id = 'g' + useId().replace(/[^a-zA-Z0-9]/g, '');
  const dec = o.dec ?? 1;
  const pts = o.values.map((v, i) => [x(i), y(clamp(v, o.min, o.max))]);
  const d = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('');
  const grid = [0, 1, 2, 3, 4].map((k) => {
    const v = o.min + ((o.max - o.min) * k) / 4;
    const yy = y(v);
    return (
      <g key={k}>
        <line x1={pl} x2={W - pr} y1={yy} y2={yy} stroke="#e6eeeb" />
        <text x={pl - 6} y={yy + 3.5} textAnchor="end">
          {fmt(v, dec)}
        </text>
      </g>
    );
  });
  let warn = null;
  if (o.warn != null) {
    const yy = y(o.warn);
    const below = o.dir !== 'above';
    warn = (
      <>
        <rect
          x={pl}
          y={below ? yy : pt}
          width={W - pl - pr}
          height={below ? H - pb - yy : yy - pt}
          fill="#d98a1c"
          opacity=".07"
        />
        <line x1={pl} x2={W - pr} y1={yy} y2={yy} stroke="#d98a1c" strokeDasharray="4 4" />
        <text x={W - pr} y={yy - 5} textAnchor="end" style={{ fill: '#a5650d' }}>
          warning {fmt(o.warn, dec)}
        </text>
      </>
    );
  }
  const times: JSX.Element[] = [];
  if (o.times) {
    const every = Math.max(1, Math.round((n - 1) / 4)); // 24 for the 97-point (15-minute) series, like the prototype
    for (let i = 0; i < n - 1 - every / 2; i += every)
      times.push(
        <text key={i} x={x(i)} y={H - 8} textAnchor={i ? 'middle' : 'start'}>
          {hhmm(o.times[i])}
        </text>,
      );
    times.push(
      <text key="now" x={x(n - 1)} y={H - 8} textAnchor="end">
        now
      </text>,
    );
  }
  const e = pts[n - 1];
  const mp = o.mark ? pts[o.mark.i] : null;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={o.label || 'Chart'}>
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={o.color} stopOpacity=".22" />
          <stop offset="1" stopColor={o.color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {grid}
      {warn}
      <path d={`${d}L${x(n - 1)} ${H - pb}L${pl} ${H - pb}Z`} fill={`url(#${id})`} />
      <path d={d} fill="none" stroke={o.color} strokeWidth="2" strokeLinejoin="round" />
      {times}
      {mp && o.mark && (
        <>
          <circle cx={mp[0]} cy={mp[1]} r="4" fill="#fff" stroke="#d6453d" strokeWidth="2" />
          <text x={mp[0] + 8} y={mp[1] + 14} style={{ fill: '#b2322b' }}>
            {o.mark.label}
          </text>
        </>
      )}
      {e && (
        <>
          <circle cx={e[0]} cy={e[1]} r="7" fill={o.color} opacity=".18" />
          <circle cx={e[0]} cy={e[1]} r="3.5" fill={o.color} />
        </>
      )}
    </svg>
  );
}

export function Spark({ values, color }: { values: number[]; color: string }) {
  const W = 200;
  const H = 36;
  if (values.length < 2) return <svg className="spark" viewBox={`0 0 ${W} ${H}`} aria-hidden="true" />;
  const mn = Math.min(...values);
  const mx = Math.max(...values);
  const r = mx - mn || 1;
  const d = values
    .map(
      (v, i) =>
        (i ? 'L' : 'M') +
        ((W * i) / (values.length - 1)).toFixed(1) +
        ' ' +
        (3 + (H - 6) * (1 - (v - mn) / r)).toFixed(1),
    )
    .join('');
  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function BarChart({ basins }: { basins: { name: string; revenue: number; costs: number }[] }) {
  const W = 640;
  const H = 230;
  const pl = 52;
  const pr = 10;
  const pt = 14;
  const pb = 30;
  const top = Math.max(26000, ...basins.map((b) => Math.max(b.revenue, b.costs)));
  const mx = top <= 26000 ? 26000 : Math.ceil(top / 4000) * 4000;
  const y = (v: number) => pt + (H - pt - pb) * (1 - v / mx);
  const cw = (W - pl - pr) / Math.max(1, basins.length);
  return (
    <svg className="bars" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Revenue and total costs per basin">
      {[0, 1, 2, 3, 4].map((k) => {
        const v = (mx * k) / 4;
        return (
          <g key={k}>
            <line x1={pl} x2={W - pr} y1={y(v)} y2={y(v)} stroke="#e6eeeb" />
            <text x={pl - 6} y={y(v) + 3.5} textAnchor="end">
              {k ? '€' + (v / 1000).toFixed(1) + 'k' : '€0'}
            </text>
          </g>
        );
      })}
      {basins.map((b, i) => {
        const x0 = pl + i * cw + cw * 0.2;
        const bw = cw * 0.28;
        return (
          <g key={b.name}>
            <rect
              x={x0}
              y={y(b.revenue)}
              width={bw}
              height={H - pb - y(b.revenue)}
              rx="4"
              fill="#1d6f6a"
              className="grow"
              style={{ animationDelay: `${i * 0.08}s` }}
            >
              <title>
                {b.name} revenue {eur(b.revenue)}
              </title>
            </rect>
            <rect
              x={x0 + bw + 4}
              y={y(b.costs)}
              width={bw}
              height={H - pb - y(b.costs)}
              rx="4"
              fill="#9cc9bf"
              className="grow"
              style={{ animationDelay: `${i * 0.08 + 0.04}s` }}
            >
              <title>
                {b.name} costs {eur(b.costs)}
              </title>
            </rect>
            <text x={x0 + bw + 2} y={H - 10} textAnchor="middle">
              {b.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

const CHART_RANGE: Record<Metric, [number, number, number]> = { do: [3, 10, 2], temp: [14, 32, 1], ph: [6.5, 9, 2] };

/** The basin chart of the prototype (basinChart): range, warning line, overnight-low marker. */
export function basinChartProps(
  b: Basin,
  m: Metric,
  series: { times: string[]; values: number[] },
  h = 230,
): LineChartProps {
  const t = b.thr;
  const thr = m === 'do' ? t.do.warn : m === 'ph' ? t.ph.max : t.temp.max;
  let [mn, mx] = CHART_RANGE[m];
  const dec = CHART_RANGE[m][2];
  const vals = series.values;
  if (m === 'temp') {
    const lo = Math.min(...vals);
    const hi = Math.max(...vals, thr ?? -Infinity);
    mn = Math.floor(lo - 1);
    mx = Math.ceil(hi + 0.5);
  } else {
    // widen the fixed range if a reading falls outside it
    mn = Math.min(mn, Math.floor(Math.min(...vals)));
    mx = Math.max(mx, Math.ceil(Math.max(...vals)));
  }
  let mark = null;
  if (m === 'do' && t.do.warn != null) {
    let mi = 0;
    vals.forEach((v, i) => {
      if (v < vals[mi]) mi = i;
    });
    if (vals[mi] < t.do.warn) mark = { i: mi, label: hhmm(series.times[mi]) + ' · ' + fmt(vals[mi], 2) };
  }
  return {
    values: vals,
    times: series.times,
    min: mn,
    max: mx,
    dec,
    warn: thr,
    dir: m === 'do' ? 'below' : 'above',
    color: '#1d6f6a',
    h,
    label: `${METRIC[m].label} in ${b.name}, last 24 hours`,
    mark,
  };
}

/** Line chart with the hover tooltip of the basin page. */
export function HoverChart({ props, metric }: { props: LineChartProps; metric: Metric }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const n = props.values.length;
  return (
    <div
      className="chart-wrap"
      ref={wrap}
      onMouseMove={(e) => {
        const svg = wrap.current?.querySelector('svg');
        if (!svg || !wrap.current) return;
        const r = svg.getBoundingClientRect();
        const vx = ((e.clientX - r.left) / r.width) * 640;
        const i = clamp(Math.round(((vx - 40) / (640 - 56)) * (n - 1)), 0, n - 1);
        const w = wrap.current.getBoundingClientRect();
        const u = METRIC[metric].unit;
        setTip({
          x: e.clientX - w.left,
          y: e.clientY - w.top,
          text:
            (i === n - 1 ? 'now' : hhmm(props.times![i])) +
            ' · ' +
            fmt(props.values[i], METRIC[metric].dec) +
            (u ? ' ' + u : ''),
        });
      }}
      onMouseLeave={() => setTip(null)}
    >
      <div className="chart" id="detailChart">
        <LineChart {...props} />
      </div>
      <div className="tip" style={tip ? { display: 'block', left: tip.x, top: tip.y } : undefined}>
        {tip?.text}
      </div>
    </div>
  );
}

/** Semicircle gauge with the species' safe band. */
export function Gauge({ b, m }: { b: Basin; m: Metric }) {
  const v = b.live[m] ?? 0;
  const t = b.thr;
  const tmin = t.temp.min ?? 10;
  const tmax = t.temp.max ?? 30;
  const R: [number, number] = m === 'do' ? [0, 12] : m === 'ph' ? [5.5, 9.5] : [tmin - 6, tmax + 6];
  const safe: [number, number] =
    m === 'do' ? [t.do.warn ?? 5, R[1]] : m === 'ph' ? [t.ph.min ?? 6.5, t.ph.max ?? 8.5] : [tmin, tmax];
  const cx = 70;
  const cy = 72;
  const r = 56;
  const P = (val: number) => {
    const a = Math.PI * (1 - (clamp(val, R[0], R[1]) - R[0]) / (R[1] - R[0]));
    return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
  };
  const arc = (a: number, b2: number, col: string, w: number) => {
    const p1 = P(a);
    const p2 = P(b2);
    return (
      <path
        d={`M${p1[0].toFixed(1)} ${p1[1].toFixed(1)}A${r} ${r} 0 0 1 ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`}
        fill="none"
        stroke={col}
        strokeWidth={w}
        strokeLinecap="round"
      />
    );
  };
  const st = b.cls[m];
  const col = st === 'bad' ? '#d6453d' : st === 'meh' ? '#d98a1c' : '#1d6f6a';
  const pv = P(v);
  return (
    <svg
      viewBox="0 0 140 84"
      role="img"
      aria-label={`${METRIC[m].label} ${fmt(v, METRIC[m].dec)}, safe range ${safe[0]} to ${safe[1]}`}
    >
      {arc(R[0], R[1], '#e6efec', 10)}
      {arc(safe[0], safe[1], '#bfe3d8', 10)}
      {m === 'do' && t.do.crit != null && t.do.warn != null && (
        <>
          {arc(t.do.crit, t.do.warn, '#f6dcb2', 10)}
          {arc(R[0], t.do.crit, '#f4c6c2', 10)}
        </>
      )}
      <circle cx={pv[0].toFixed(1)} cy={pv[1].toFixed(1)} r="7" fill="#fff" stroke={col} strokeWidth="3" />
      <text x="14" y="82" fontSize="8" fill="#7b8d91" fontFamily="Geist Mono, monospace">
        {R[0]}
      </text>
      <text x="126" y="82" fontSize="8" fill="#7b8d91" textAnchor="end" fontFamily="Geist Mono, monospace">
        {R[1]}
      </text>
    </svg>
  );
}

export const tankLevel = (b: Basin) => clamp(Math.round((b.sat ?? 60) * 0.85), 18, 92);

export function Tank({ b }: { b: Basin }) {
  return (
    <div className={`tank ${b.status}`} style={{ '--lvl': tankLevel(b) + '%' } as CSSProperties}>
      <div className="water">
        <svg className="wv back" viewBox="0 0 400 10" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 6Q25 0 50 6T100 6T150 6T200 6T250 6T300 6T350 6T400 6V10H0Z" fill="currentColor" />
        </svg>
        <svg className="wv" viewBox="0 0 400 10" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 5Q25 10 50 5T100 5T150 5T200 5T250 5T300 5T350 5T400 5V10H0Z" fill="currentColor" />
        </svg>
      </div>
      <span className="tank-fish" style={{ bottom: '14%', animationDuration: '17s' }}>
        <FishSvg />
      </span>
      <span className="tank-fish" style={{ bottom: '34%', width: 14, animationDuration: '23s', animationDelay: '-9s' }}>
        <FishSvg />
      </span>
      <span className="tank-fish" style={{ bottom: '8%', width: 16, animationDuration: '20s', animationDelay: '-4s' }}>
        <FishSvg />
      </span>
      <span className="tank-lbl mono">{b.sat != null ? Math.round(b.sat) : '–'}% O₂ saturation</span>
    </div>
  );
}
