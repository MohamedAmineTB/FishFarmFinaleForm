// Shift report (screen 32): send a report to the owner's inbox, see your recent reports.
import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { api } from '../../api/client';
import { useApi, useLive } from '../../api/realtime';
import type { Report } from '../../api/types';
import { useTitle } from '../../App';
import { useEnter } from '../../components/Home';
import { Field, ValidatedForm, useToast } from '../../components/ui';
import { fmtDate } from '../../lib/format';

export default function ShiftReport() {
  useTitle('Shift report');
  const toast = useToast();
  const { live } = useLive();
  const loc = useLocation();
  const preset = (loc.state as { basin?: string } | null)?.basin ?? '';
  const { data, reload } = useApi<Report[]>('/api/reports/mine', []);
  const [formKey, setFormKey] = useState(0);
  const [err, setErr] = useState('');
  useEnter(true, 'shift');
  return (
    <div className="grid g2">
      <div className="tile">
        <h3>Send your shift report</h3>
        <p className="mini">The owner sees it in the reports inbox right away.</p>
        <ValidatedForm
          key={formKey}
          onValid={async (d) => {
            setErr('');
            try {
              await api('/api/reports', { body: { title: d.title.trim(), body: d.body.trim(), basin_id: d.basin || null } });
              toast(
                <>
                  <b>Sent</b> · your report is in the owner's inbox
                </>,
              );
              setFormKey((k) => k + 1);
              reload();
            } catch (e) {
              setErr((e as Error).message);
            }
          }}
        >
          <Field id="srTitle" name="title" label="Report title" rule={{ required: true }} placeholder="Morning shift: Basin 3 feeding" />
          <label className="field" htmlFor="srBasin">
            Basin
            <select id="srBasin" name="basin" defaultValue={preset}>
              <option value="">All basins</option>
              {(live?.basins ?? []).map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </label>
          <Field id="srBody" name="body" textarea label="What did you see?" rule={{ required: true }} placeholder="Fish behaviour, feeding, water colour, equipment…" />
          {err && <div className="form-err">{err}</div>}
          <button className="small-btn primary" style={{ justifySelf: 'start' }} type="submit">
            Send report
          </button>
        </ValidatedForm>
      </div>
      <div className="tile">
        <h3>Your recent reports</h3>
        {data && data.length ? (
          <div className="list">
            {data.map((r) => (
              <div key={r.id} style={{ borderBottom: '1px solid var(--line)', paddingBottom: 8 }}>
                <b>{r.title}</b>
                <div className="mini mono">{fmtDate(r.time)}</div>
              </div>
            ))}
          </div>
        ) : (
          <p className="mini">You haven't sent a report yet.</p>
        )}
      </div>
    </div>
  );
}
