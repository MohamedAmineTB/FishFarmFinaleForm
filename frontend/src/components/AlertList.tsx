// Alert rows with the tick-off flow: tick -> resolve dialog (required note) -> green pop -> moves to Done.
// Ticking a green check asks to reopen.
import { useState, type ReactNode } from 'react';
import { api } from '../api/client';
import { useLive } from '../api/realtime';
import { useSession } from '../api/session';
import type { Alert } from '../api/types';
import { useAssistant } from '../assistant/context';
import { hhmm } from '../lib/format';
import { Check, CheckSm, Icon } from './Icons';
import { Field, Modal, ValidatedForm, sevClass, useToast } from './ui';

function AlertItem({ a, justDone, onCheck }: { a: Alert; justDone: string | null; onCheck: (a: Alert) => void }) {
  const ai = useAssistant();
  const done = a.resolved || justDone !== null;
  const who = a.kind === 'sensor' ? 'the technician' : 'the worker on shift';
  return (
    <div
      className={`alert sev-${a.severity}${a.resolved && justDone === null ? ' done' : ''}${justDone !== null ? ' just-done' : ''}`}
      data-aid={a.id}
    >
      <span className="stripe" />
      <button
        className={`check${done ? ' on' : ''}`}
        type="button"
        aria-pressed={done}
        aria-label={`${done ? 'Resolved. Click to reopen' : 'Mark as resolved'}: ${a.title}`}
        title={done ? 'Resolved · click to reopen' : 'Mark as resolved'}
        onClick={() => onCheck(a)}
      >
        <Check />
      </button>
      <div>
        <div className="row" style={{ justifyContent: 'flex-start', gap: 8 }}>
          <h4>{a.title}</h4>
          <span className={`badge ${sevClass(a.severity)}`}>{a.severity}</span>
          <span className="badge" style={{ background: '#eef3f2', color: '#3b5559' }}>
            {a.kind === 'sensor' ? 'hardware' : 'water'}
          </span>
        </div>
        <p>
          <b style={{ color: 'var(--ink)' }}>{a.basin}</b> · {a.species_name} · {a.metric_label} · {hhmm(a.time)}
        </p>
        <p>{a.text}</p>
        <p className={`a-status${done ? ' ok' : ''}`}>
          {justDone !== null
            ? `✓ Resolved by ${justDone} just now`
            : a.resolved
              ? `✓ Resolved by ${a.by ?? ''} at ${hhmm(a.resolved_at ?? Date.now())} · “${a.note ?? ''}”`
              : `Open · waiting for ${who}`}
        </p>
      </div>
      <div className="acts">
        {!a.resolved && (
          <button className="small-btn" onClick={() => ai.ask(`Explain alert ${a.id}`)}>
            <Icon name="chat" size={14} />
            Explain
          </button>
        )}
      </div>
    </div>
  );
}

export function AlertList({ alerts, onChanged, empty }: { alerts: Alert[]; onChanged: () => void; empty?: ReactNode }) {
  const { me } = useSession();
  const { reload } = useLive();
  const toast = useToast();
  const [resolving, setResolving] = useState<Alert | null>(null);
  const [reopening, setReopening] = useState<Alert | null>(null);
  const [just, setJust] = useState<Record<string, string>>({});
  // rows that were just ticked stay in place (green) until the pop animation ends, even if a refresh removes them
  const [held, setHeld] = useState<Record<string, { a: Alert; i: number }>>({});
  const rows = alerts.filter((a) => !held[a.id]);
  Object.values(held)
    .sort((x, y) => x.i - y.i)
    .forEach(({ a, i }) => rows.splice(Math.min(i, rows.length), 0, a));
  const [err, setErr] = useState('');

  const onCheck = (a: Alert) => {
    if (just[a.id]) return;
    setErr('');
    if (a.resolved) setReopening(a);
    else setResolving(a);
  };
  const sensor = resolving?.kind === 'sensor';
  return (
    <>
      {rows.length
        ? rows.map((a) => <AlertItem key={a.id} a={a} justDone={just[a.id] ?? null} onCheck={onCheck} />)
        : empty}
      <Modal open={!!resolving} onClose={() => setResolving(null)} label="Resolve alert">
        {resolving && (
          <>
            <h3>{sensor ? 'Mark probe repaired' : 'Resolve alert'}</h3>
            <p className="mini">
              {resolving.basin} · {resolving.title}
            </p>
            <ValidatedForm
              onValid={async (d) => {
                const a = resolving;
                try {
                  await api(`/api/alerts/${a.id}/resolve`, { body: { note: d.note.trim() } });
                } catch (e) {
                  setErr((e as Error).message);
                  return;
                }
                setResolving(null);
                toast(
                  <>
                    <b>✓ Resolved</b> · {a.basin} · {a.title}
                  </>,
                );
                setJust((j) => ({ ...j, [a.id]: me!.user.name }));
                setHeld((h) => ({ ...h, [a.id]: { a, i: alerts.findIndex((x) => x.id === a.id) } }));
                reload();
                window.setTimeout(() => {
                  setJust((j) => {
                    const n = { ...j };
                    delete n[a.id];
                    return n;
                  });
                  setHeld((h) => {
                    const n = { ...h };
                    delete n[a.id];
                    return n;
                  });
                  onChanged();
                }, 1100);
              }}
            >
              <Field
                id="resNote"
                name="note"
                textarea
                label={sensor ? 'What did you repair?' : 'What did you do?'}
                rule={{ required: true }}
                placeholder={sensor ? 'Cleaned and recalibrated the probe…' : 'Ran the aerator, cut the evening feed…'}
              />
              {err && <div className="form-err">{err}</div>}
              <div className="row" style={{ justifyContent: 'flex-end' }}>
                <button className="small-btn" type="button" onClick={() => setResolving(null)}>
                  Cancel
                </button>
                <button className="small-btn ok" type="submit">
                  <CheckSm />
                  {sensor ? 'Mark repaired' : 'Mark as resolved'}
                </button>
              </div>
            </ValidatedForm>
          </>
        )}
      </Modal>
      <Modal open={!!reopening} onClose={() => setReopening(null)} label="Reopen alert">
        {reopening && (
          <>
            <h3>Reopen this alert?</h3>
            <p className="mini">
              {reopening.basin} · {reopening.title}. It was resolved by {reopening.by ?? ''}: “{reopening.note ?? ''}”.
            </p>
            <div className="acts-row">
              <button className="small-btn" onClick={() => setReopening(null)}>
                Keep it resolved
              </button>
              <button
                className="small-btn primary"
                onClick={async () => {
                  const a = reopening;
                  await api(`/api/alerts/${a.id}/reopen`, { method: 'POST' });
                  setReopening(null);
                  toast(
                    <>
                      <b>Reopened</b> · {a.title}
                    </>,
                  );
                  reload();
                  onChanged();
                }}
              >
                Reopen alert
              </button>
            </div>
          </>
        )}
      </Modal>
    </>
  );
}
