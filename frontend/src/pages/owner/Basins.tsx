// Basins (screen 11): status counts and a 2-column grid of live basin cards.
import { useState } from 'react';
import { useLive } from '../../api/realtime';
import { useSession } from '../../api/session';
import { useTitle } from '../../App';
import { BasinCard } from '../../components/BasinCard';
import { useEnter } from '../../components/Home';
import { AddBasinSheet, FirstBasin } from './AddBasin';

export default function Basins() {
  useTitle('Basins');
  const { live, reload } = useLive();
  const { me } = useSession();
  const [adding, setAdding] = useState(false);
  useEnter(!!live, 'basins');
  if (!live) return null;
  const bs = live.basins;
  const owner = me?.role === 'owner';
  if (!bs.length) return owner ? <FirstBasin onChange={reload} /> : <div className="tile none"><strong>No basins yet.</strong><span>Your farm owner hasn't added any basin.</span></div>;
  const probes = bs.reduce((n, b) => n + Object.keys(b.sensors).length, 0);
  const count = (s: string) => bs.filter((b) => b.status === s).length;
  return (
    <>
      <div className="section-title">
        <p className="mini">Live readings from {probes} probes. The water level shows oxygen saturation; colour shows status.</p>
        <div className="row">
          <span className="badge b-healthy">{count('healthy')} healthy</span>
          <span className="badge b-warning">{count('warning')} warning</span>
          <span className="badge b-critical">{count('critical')} critical</span>
          {owner && (
            <button className="small-btn primary" onClick={() => setAdding(true)}>
              + Add basin
            </button>
          )}
        </div>
      </div>
      <div className="grid g2">
        {bs.map((b) => (
          <BasinCard b={b} key={b.id} />
        ))}
      </div>
      {owner && <AddBasinSheet open={adding} onClose={() => setAdding(false)} onDone={reload} />}
    </>
  );
}
