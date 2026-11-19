// "Add your first basin" side sheet and the empty state of a new farm.
import { useState } from 'react';
import { api } from '../../api/client';
import { useLive } from '../../api/realtime';
import { Field, Sheet, ValidatedForm, useToast } from '../../components/ui';

export const SPECIES = [
  ['tilapia', 'Nile tilapia'],
  ['rainbow_trout', 'Rainbow trout'],
  ['common_carp', 'Common carp'],
  ['sea_bass', 'European sea bass'],
  ['sea_bream', 'Gilthead sea bream'],
  ['atlantic_salmon', 'Atlantic salmon'],
];

export function AddBasinSheet({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [err, setErr] = useState('');
  return (
    <Sheet open={open} onClose={onClose} label="Add a basin">
      <h3>Add a basin</h3>
      <p className="mini">
        We create three probes for it (temperature, pH and dissolved oxygen) with the safe ranges of the species.
        Readings start within a few seconds.
      </p>
      <ValidatedForm
        onValid={async (d) => {
          setErr('');
          try {
            await api('/api/basins', {
              body: {
                name: d.name.trim(),
                species: d.species,
                capacity: Number(d.capacity),
                fish_count: Number(d.fish),
              },
            });
            toast(
              <>
                <b>Basin added</b> · {d.name.trim()}
              </>,
            );
            onDone();
            onClose();
          } catch (e) {
            setErr((e as Error).message);
          }
        }}
      >
        <Field id="bName" name="name" label="Basin name" rule={{ required: true }} placeholder="Basin 1" />
        <label className="field" htmlFor="bSpecies">
          Species
          <select id="bSpecies" name="species">
            {SPECIES.map(([k, l]) => (
              <option key={k} value={k}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <div className="two">
          <Field id="bCap" name="capacity" label="Volume (m³)" type="number" min={1} rule={{ required: true }} />
          <Field id="bFish" name="fish" label="Fish count" type="number" min={0} rule={{ required: true }} />
        </div>
        {err && <div className="form-err">{err}</div>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="small-btn" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="small-btn primary" type="submit">
            Add basin
          </button>
        </div>
      </ValidatedForm>
    </Sheet>
  );
}

export function FirstBasin({ onChange }: { onChange: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const { reload } = useLive();
  return (
    <div className="tile first-basin">
      <span className="big-check" aria-hidden="true">
        <svg
          viewBox="0 0 24 24"
          width="28"
          height="28"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 9c3 2 6 2 9 0s6-2 9 0M3 14c3 2 6 2 9 0s6-2 9 0M3 19c3 2 6 2 9 0s6-2 9 0" />
        </svg>
      </span>
      <strong>Add your first basin.</strong>
      <span>Each basin gets three probes. Live readings, alerts and charts start as soon as it exists.</span>
      <div className="row">
        <button className="btn" type="button" onClick={() => setOpen(true)}>
          Add your first basin
        </button>
        <button
          className="btn ghost"
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await api('/api/demo/load', { method: 'POST' });
              toast(
                <>
                  <b>Demo farm loaded</b> · 4 basins, 30 days of readings and a demo team
                </>,
              );
              reload();
              onChange();
            } catch (e) {
              toast(<>{(e as Error).message}</>);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? 'Loading the demo farm…' : 'Load demo farm'}
        </button>
      </div>
      <AddBasinSheet
        open={open}
        onClose={() => setOpen(false)}
        onDone={() => {
          reload();
          onChange();
        }}
      />
    </div>
  );
}
