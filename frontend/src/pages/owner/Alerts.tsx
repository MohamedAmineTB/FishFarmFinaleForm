// Alerts (screens 14-17, 31, 41): Open / Done tabs, tick-off flow. Each role sees its own alerts.
import { useState } from 'react';
import { useApi } from '../../api/realtime';
import { useSession } from '../../api/session';
import type { Alert } from '../../api/types';
import { useTitle } from '../../App';
import { AlertList } from '../../components/AlertList';
import { useEnter } from '../../components/Home';
import { Check } from '../../components/Icons';
import { LoadError } from './Overview';

export default function Alerts() {
  const { me } = useSession();
  const role = me!.role;
  useTitle(role === 'technician' ? 'Hardware alerts' : 'Alerts');
  const [tab, setTab] = useState<'open' | 'resolved'>('open');
  const { data, error, reload } = useApi<Alert[]>('/api/alerts?status=all', ['alert']);
  useEnter(!!data, 'alerts');
  if (!data) return <LoadError error={error} />;
  const open = data.filter((a) => !a.resolved);
  const done = data.filter((a) => a.resolved).sort((a, b) => (b.resolved_at ?? '').localeCompare(a.resolved_at ?? ''));
  const list = tab === 'resolved' ? done : open;
  const head =
    role === 'owner'
      ? 'Every alert on the farm. Tick the circle when a problem is handled; the team sees who closed it and why.'
      : role === 'worker'
        ? 'Water alerts for every basin. Tick the circle when you have dealt with one and add a short note.'
        : 'Probes that look stuck, drifting or broken. Tick the circle after the repair.';
  return (
    <>
      <div className="section-title">
        <p className="mini" style={{ maxWidth: '70ch' }}>
          {head}
        </p>
        <div className="tabs" role="tablist" aria-label="Alert status">
          <button role="tab" aria-selected={tab !== 'resolved'} onClick={() => setTab('open')}>
            Open · {open.length}
          </button>
          <button role="tab" aria-selected={tab === 'resolved'} onClick={() => setTab('resolved')}>
            Done · {done.length}
          </button>
        </div>
      </div>
      <div className="list">
        <AlertList
          alerts={list}
          onChanged={reload}
          empty={
            tab === 'resolved' ? (
              <div className="tile none">
                <strong>Nothing closed yet.</strong>
                <span>Alerts you tick off appear here with who closed them and the note.</span>
              </div>
            ) : (
              <div className="tile none">
                <span className="big-check">
                  <Check />
                </span>
                <strong>All clear.</strong>
                <span>Every alert is handled. The alert engine keeps checking every basin.</span>
              </div>
            )
          }
        />
      </div>
    </>
  );
}
