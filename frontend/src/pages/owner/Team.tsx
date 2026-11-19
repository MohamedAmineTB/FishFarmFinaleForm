// Team (screens 21-23): members table, add-member side sheet, permissions side sheet (saved instantly).
import { useMemo, useState } from 'react';
import { ApiError, api } from '../../api/client';
import { useApi } from '../../api/realtime';
import type { Member, Perms } from '../../api/types';
import { useTitle } from '../../App';
import { useEnter } from '../../components/Home';
import { Field, Sheet, ValidatedForm, useToast } from '../../components/ui';
import { initials } from '../../lib/format';
import { LoadError } from './Overview';

const PERMS: [keyof Perms, string, string][] = [
  ['reports', 'Reports', 'Send shift reports and see the inbox'],
  ['alerts', 'Alerts', 'See and resolve alerts'],
  ['basins', 'Basins', 'Open basin dashboards'],
  ['sensors', 'Sensors', 'See probe health'],
  ['maintenance', 'Maintenance', 'Log and update maintenance'],
];
const roleLabel = (r: string) => (r === 'worker' ? 'Worker' : 'Technician');

export default function Team() {
  useTitle('Team');
  const toast = useToast();
  const { data, error, reload, setData } = useApi<Member[]>('/api/team', ['team']);
  const [adding, setAdding] = useState(false);
  const [permFor, setPermFor] = useState<string | null>(null);
  const [setErr, setSetErr] = useState<((n: string, m: string) => void) | null>(null);
  const tempPass = useMemo(() => `farm-${Math.floor(1000 + Math.random() * 9000)}`, [adding]); // eslint-disable-line react-hooks/exhaustive-deps
  useEnter(!!data, 'team');
  if (!data) return <LoadError error={error} />;
  const member = data.find((m) => m.id === permFor) ?? null;

  const flip = async (m: Member, k: keyof Perms) => {
    const on = !m.permissions[k];
    setData(data.map((x) => (x.id === m.id ? { ...x, permissions: { ...x.permissions, [k]: on } } : x)));
    try {
      await api(`/api/team/${m.id}/permissions`, { method: 'PATCH', body: { permissions: { [k]: on } } });
      toast(
        <>
          <b>Saved</b> · {m.name} {on ? 'can now' : 'can no longer'} see{' '}
          {PERMS.find((p) => p[0] === k)![1].toLowerCase()}
        </>,
      );
    } catch (e) {
      setData(data);
      toast(<>{(e as Error).message}</>);
    }
  };

  return (
    <>
      <div className="tile">
        <div className="section-title">
          <h3>Workers and technicians</h3>
          <button className="small-btn primary" onClick={() => setAdding(true)}>
            + Add member
          </button>
        </div>
        {data.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Role</th>
                  <th>Shift</th>
                  <th>Can see</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((t) => (
                  <tr key={t.id}>
                    <td>
                      <span className="person">
                        <span className={`avatar${t.role === 'technician' ? ' tech' : ''}`}>{initials(t.name)}</span>
                        <div>
                          <b>{t.name}</b>
                          <span>{t.email}</span>
                        </div>
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${t.role === 'worker' ? 'b-healthy' : 'b-info'}`}>
                        {roleLabel(t.role)}
                      </span>
                    </td>
                    <td className="mono">
                      {t.shift_start}–{t.shift_end}
                    </td>
                    <td>
                      <span className="perm-chips">
                        {PERMS.map(([k, l]) => (
                          <span key={k} className={t.permissions[k] ? '' : 'off'}>
                            {l}
                          </span>
                        ))}
                      </span>
                    </td>
                    <td>
                      <button className="small-btn" onClick={() => setPermFor(t.id)}>
                        Edit permissions
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mini">
            No team members yet. Add your workers and technicians: they sign in on the team sign-in page.
          </p>
        )}
        <span className="mini">
          Changes apply right away: the member's menu updates instantly, even if they are signed in.
        </span>
      </div>

      <Sheet open={adding} onClose={() => setAdding(false)} label="Add a team member">
        <h3>Add a team member</h3>
        <p className="mini">
          We create their account now. They sign in on the team sign-in page with this email and password.
        </p>
        <ValidatedForm
          setError={(fn) => setSetErr(() => fn)}
          onValid={async (d) => {
            try {
              await api('/api/team', {
                body: {
                  name: d.name.trim(),
                  email: d.email.trim().toLowerCase(),
                  password: d.pass,
                  role: d.role.toLowerCase(),
                  shift_start: d.s,
                  shift_end: d.e,
                },
              });
              setAdding(false);
              toast(
                <>
                  <b>Account created</b> · {d.name.trim()} can sign in with {d.email.trim().toLowerCase()}
                </>,
              );
              reload();
            } catch (e) {
              if (e instanceof ApiError && e.code === 'email_taken')
                setErr?.('email', 'This email already has an account.');
              else toast(<>{(e as Error).message}</>);
            }
          }}
        >
          <Field id="mName" name="name" label="Full name" rule={{ required: true }} />
          <Field id="mEmail" name="email" label="Email" type="email" rule={{ required: true, email: true }} />
          <Field
            id="mPass"
            name="pass"
            label="Temporary password"
            type="text"
            rule={{ required: true, min: 8 }}
            defaultValue={tempPass}
            key={tempPass}
          />
          <label className="field" htmlFor="mRole">
            Role
            <select id="mRole" name="role">
              <option>Worker</option>
              <option>Technician</option>
            </select>
          </label>
          <div className="two">
            <label className="field" htmlFor="mS">
              Shift start
              <input id="mS" name="s" type="time" defaultValue="06:00" required />
            </label>
            <label className="field" htmlFor="mE">
              Shift end
              <input id="mE" name="e" type="time" defaultValue="14:00" required />
            </label>
          </div>
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button className="small-btn" type="button" onClick={() => setAdding(false)}>
              Cancel
            </button>
            <button className="small-btn primary" type="submit">
              Create account
            </button>
          </div>
        </ValidatedForm>
      </Sheet>

      <Sheet open={!!member} onClose={() => setPermFor(null)} label="Edit permissions">
        {member && (
          <>
            <span className="person">
              <span className={`avatar${member.role === 'technician' ? ' tech' : ''}`}>{initials(member.name)}</span>
              <div>
                <b>{member.name}</b>
                <span>
                  {roleLabel(member.role)} · {member.shift_start}–{member.shift_end}
                </span>
              </div>
            </span>
            <h3>What can {member.name.split(' ')[0]} see?</h3>
            <div>
              {PERMS.map(([k, l, d]) => (
                <div className="perm-row" key={k}>
                  <div>
                    <b>{l}</b>
                    <span>{d}</span>
                  </div>
                  <button
                    className="switch"
                    type="button"
                    role="switch"
                    aria-checked={!!member.permissions[k]}
                    aria-label={l}
                    onClick={() => flip(member, k)}
                  />
                </div>
              ))}
            </div>
            <p className="mini">Saved instantly. Their menu shows only the pages you switch on.</p>
            <button className="small-btn" style={{ justifySelf: 'start' }} onClick={() => setPermFor(null)}>
              Done
            </button>
          </>
        )}
      </Sheet>
    </>
  );
}
