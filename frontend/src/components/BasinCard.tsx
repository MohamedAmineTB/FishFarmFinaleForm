import { useNavigate } from 'react-router-dom';
import { useSession } from '../api/session';
import type { Basin } from '../api/types';
import { fmt } from '../lib/format';
import { basinPath } from '../lib/nav';
import { Tank } from './Charts';
import { Badge } from './ui';

export function BasinCard({ b }: { b: Basin }) {
  const nav = useNavigate();
  const { me } = useSession();
  const open = () => nav(basinPath(me!.role, b.id));
  return (
    <div
      className="tile basin-card"
      tabIndex={0}
      role="button"
      aria-label={`Open ${b.name}`}
      onClick={open}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), open())}
    >
      <div className="row">
        <div>
          <h3>{b.name}</h3>
          <span className="mini">{b.species_name}</span>
        </div>
        <span>
          <Badge st={b.status} />
        </span>
      </div>
      <Tank b={b} />
      <div className="readings3">
        <div>
          <span>Oxygen mg/L</span>
          <b className={b.cls.do}>{fmt(b.live.do, 2)}</b>
        </div>
        <div>
          <span>Temp °C</span>
          <b className={b.cls.temp}>{fmt(b.live.temp, 1)}</b>
        </div>
        <div>
          <span>pH</span>
          <b className={b.cls.ph}>{fmt(b.live.ph, 2)}</b>
        </div>
      </div>
      <div className="basin-foot">
        <span>
          {b.fish.toLocaleString('en-US')} fish · {b.capacity} m³ · {b.density.toFixed(1)} per m³
        </span>
        <span className="badge b-est">
          {b.risk != null ? `Low-O₂ risk ${Math.round(b.risk * 100)}% · estimate` : 'Low-O₂ risk · estimate pending'}
        </span>
      </div>
    </div>
  );
}
