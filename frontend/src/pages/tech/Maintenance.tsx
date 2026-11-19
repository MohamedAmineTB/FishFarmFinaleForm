// Maintenance (screen 43): log a calibration / repair / replacement, update task status.
import { useState } from 'react';
import { api } from '../../api/client';
import { useApi } from '../../api/realtime';
import type { Task } from '../../api/types';
import { useTitle } from '../../App';
import { useEnter } from '../../components/Home';
import { Field, ValidatedForm, useToast } from '../../components/ui';
import { STATUS_LABEL } from './Today';

interface Probe {
  id: string;
  code: string;
  basin: string;
  short: string;
}

export default function Maintenance() {
  useTitle('Maintenance');
  const toast = useToast();
  const probes = useApi<Probe[]>('/api/sensors', []);
  const tasks = useApi<Task[]>('/api/tasks?scope=all', ['task']);
  const [formKey, setFormKey] = useState(0);
  const [err, setErr] = useState('');
  useEnter(!!tasks.data, 'maintenance');
  const list = tasks.data ?? [];
  return (
    <div className="grid g2">
      <div className="tile">
        <h3>Log a calibration, repair or replacement</h3>
        <p className="mini">Logs go straight to the owner's reports inbox.</p>
        <ValidatedForm
          key={formKey}
          onValid={async (d) => {
            setErr('');
            try {
              await api('/api/maintenance', { body: { sensor_id: d.sensor, work_type: d.type, due_date: d.due, description: d.desc.trim() } });
              toast(
                <>
                  <b>Logged</b> · visible in the owner's reports
                </>,
              );
              setFormKey((k) => k + 1);
              tasks.reload();
            } catch (e) {
              setErr((e as Error).message);
            }
          }}
        >
          <label className="field" htmlFor="mtSensor">
            Probe
            <select id="mtSensor" name="sensor">
              {(probes.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.code} · {s.basin} · {s.short}
                </option>
              ))}
            </select>
          </label>
          <div className="two">
            <label className="field" htmlFor="mtType">
              Work done
              <select id="mtType" name="type">
                <option>Calibration</option>
                <option>Repair</option>
                <option>Replacement</option>
              </select>
            </label>
            <Field id="mtDue" name="due" label="Due date" type="date" rule={{ required: true }} />
          </div>
          <Field id="mtDesc" name="desc" textarea label="Description" rule={{ required: true }} placeholder="What you did and what you measured" />
          {err && <div className="form-err">{err}</div>}
          <button className="small-btn primary" style={{ justifySelf: 'start' }} type="submit">
            Save log
          </button>
        </ValidatedForm>
      </div>
      <div className="tile">
        <div className="section-title">
          <h3>Maintenance tasks</h3>
          <span className="mini">{list.filter((t) => t.status !== 'fixed').length} open</span>
        </div>
        {list.map((t) => (
          <div className="task" key={t.id}>
            <span>
              <span className="t">
                <b>{t.title}</b>
              </span>
              <span className="mini">
                {t.who} · due {t.due}
              </span>
            </span>
            <select
              aria-label={`Status of ${t.title}`}
              value={t.status}
              onChange={async (e) => {
                const status = e.target.value;
                await api(`/api/tasks/${t.id}`, { method: 'PATCH', body: { status } });
                toast(
                  <>
                    <b>Updated</b> · {t.title} is {STATUS_LABEL[status]}
                  </>,
                );
                tasks.reload();
              }}
            >
              {(['pending', 'in_progress', 'fixed'] as const).map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </select>
          </div>
        ))}
        {!list.length && <p className="mini">No tasks yet.</p>}
      </div>
    </div>
  );
}
