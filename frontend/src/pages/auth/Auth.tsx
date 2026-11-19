// Sign-in pages: /owner-auth (sign in or create a farm) and /worker-auth (team sign in).
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ApiError, api } from '../../api/client';
import { useSession } from '../../api/session';
import { useHtmlMode } from '../../App';
import { BrandSvg } from '../../components/Icons';
import { Field, ValidatedForm, useToast } from '../../components/ui';
import { WaterCanvas } from '../../components/Water';
import { fmt } from '../../lib/format';
import { homePath } from '../../lib/nav';

const COUNTRIES = ['France', 'Algeria', 'Morocco', 'Tunisia', 'Spain', 'Italy', 'Norway', 'Other'];

function AuthLayout({ quote, children }: { quote: ReactNode; children: ReactNode }) {
  useHtmlMode('auth');
  const [doValue, setDo] = useState<number | null>(null);
  useEffect(() => {
    const load = () =>
      api<{ do?: number }>('/api/public/showcase')
        .then((s) => s.do != null && setDo(s.do))
        .catch(() => undefined);
    load();
    const t = window.setInterval(load, 6000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <div className="auth" id="auth">
      <div className="auth-art">
        <WaterCanvas
          id="authCanvas"
          opts={{ palette: 'dark', fish: 22, top: 0.05, scale: 1.2, aerators: [0.2, 0.7] }}
        />
        <Link className="brand" to="/" aria-label="Back to the FishFarm website">
          <BrandSvg eye="#0c3038" />
          fishfarm
        </Link>
        <div>
          <p className="auth-quote" id="authQuote">
            {quote}
          </p>
          <div className="reading">
            <span className="lbl">
              <i />
              Basin 3 · dissolved oxygen · live
            </span>
            <b data-hero="do2">{fmt(doValue ?? 7.42, 2)}</b>
            <span className="u">mg/L</span>
          </div>
        </div>
        <div className="auth-meta">
          <span>4 basins</span>
          <span>12 probes</span>
          <span>a reading every 6 s</span>
          <span>3 roles</span>
        </div>
      </div>
      <div className="auth-side">
        <div className="auth-card" id="authCard">
          {children}
        </div>
      </div>
    </div>
  );
}

/** Fills email + password with a demo account and clears any errors. */
function useFill() {
  return (email: string) => {
    const f = document.querySelector('#authCard form') as HTMLFormElement | null;
    if (!f) return;
    // set the values and fire input events so the validation state clears like after typing
    for (const [name, value] of [
      ['email', email],
      ['pass', 'demo1234'],
    ]) {
      const input = f.elements.namedItem(name) as HTMLInputElement;
      input.value = value;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    (f.querySelector('button[type="submit"]') as HTMLButtonElement).focus();
  };
}

function useAfterSignIn() {
  const nav = useNavigate();
  const loc = useLocation();
  return (role: 'owner' | 'worker' | 'technician') => {
    const from = (loc.state as { from?: string } | null)?.from;
    nav(from && from.startsWith(homePath(role)) ? from : homePath(role), { replace: true });
  };
}

export function OwnerAuth() {
  const loc = useLocation();
  const [sub, setSub] = useState<'signin' | 'register'>(((loc.state as any)?.sub as 'register') || 'signin');
  const [err, setErr] = useState<ReactNode>(null);
  const [busy, setBusy] = useState(false);
  const { login, register } = useSession();
  const after = useAfterSignIn();
  const fill = useFill();
  const toast = useToast();
  const first = useRef<HTMLDivElement>(null);
  const reg = sub === 'register';

  useEffect(() => {
    setErr(null);
    window.setTimeout(() => {
      // move focus to the first field only if the user isn't already typing somewhere
      if (document.activeElement?.tagName === 'INPUT') return;
      (first.current?.querySelector('input') as HTMLInputElement | null)?.focus({ preventScroll: true });
    }, 50);
  }, [sub]);

  return (
    <AuthLayout
      quote={
        <>
          The oxygen dip came at 4 a.m. The night worker knew <em>before the fish did.</em>
        </>
      }
    >
      <span className="pill">
        <i />
        Farm owners
      </span>
      <h1>{reg ? 'Create your farm' : 'Welcome back'}</h1>
      <p className="lead">
        {reg
          ? 'Set up your farm in a minute. You add your workers and technicians afterwards.'
          : 'Sign in to see every basin, alert and report on your farm.'}
      </p>
      <div className="seg" role="tablist">
        <button type="button" role="tab" aria-selected={!reg} onClick={() => setSub('signin')}>
          Sign in
        </button>
        <button type="button" role="tab" aria-selected={reg} onClick={() => setSub('register')}>
          Create farm
        </button>
      </div>
      <div ref={first} style={{ display: 'contents' }}>
        {reg ? (
          <ValidatedForm
            key="reg"
            onValid={async (d) => {
              setBusy(true);
              setErr(null);
              try {
                await register({
                  name: d.name.trim(),
                  email: d.email.trim().toLowerCase(),
                  password: d.pass,
                  farm: d.farm.trim(),
                  company: d.company.trim(),
                  country: d.country,
                });
                toast(
                  <>
                    <b>Farm created</b> · welcome to {d.farm.trim()}
                  </>,
                );
                after('owner');
              } catch (e) {
                if (e instanceof ApiError && e.code === 'email_taken')
                  setErr(
                    <>
                      This email already has an account.{' '}
                      <a href="#signin" onClick={(ev) => (ev.preventDefault(), setSub('signin'))}>
                        Sign in instead
                      </a>
                      .
                    </>,
                  );
                else setErr((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Field id="rName" name="name" label="Your name" rule={{ required: true }} autoComplete="name" />
            <Field
              id="rEmail"
              name="email"
              label="Email"
              type="email"
              rule={{ required: true, email: true }}
              autoComplete="email"
            />
            <Field
              id="rPass"
              name="pass"
              password
              label={
                <>
                  Password <span className="mini">(at least 8 characters)</span>
                </>
              }
              rule={{ required: true, min: 8 }}
              autoComplete="new-password"
            />
            <Field id="rFarm" name="farm" label="Farm name" rule={{ required: true }} placeholder="Lac Vert" />
            <div className="two">
              <Field id="rCo" name="company" label="Company name" rule={{ required: true }} />
              <label className="field" htmlFor="rCountry">
                Country
                <select id="rCountry" name="country">
                  {COUNTRIES.map((x) => (
                    <option key={x}>{x}</option>
                  ))}
                </select>
              </label>
            </div>
            {err && (
              <div className="form-err" id="rErr">
                {err}
              </div>
            )}
            <button className="btn wide" type="submit" disabled={busy}>
              Create farm
            </button>
            <p className="mini">
              Your farm starts empty. Add your first basin, or load the demo farm to explore right away.
            </p>
          </ValidatedForm>
        ) : (
          <ValidatedForm
            key="signin"
            onValid={async (d) => {
              setBusy(true);
              setErr(null);
              try {
                const me = await login('owner', d.email.trim().toLowerCase(), d.pass);
                after(me.role);
              } catch (e) {
                if (e instanceof ApiError && e.code === 'wrong_portal')
                  setErr(
                    <>
                      This is a {e.detail.role} account. Use <Link to="/worker-auth">team sign in</Link>.
                    </>,
                  );
                else setErr((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Field
              id="oEmail"
              name="email"
              label="Email"
              type="email"
              rule={{ required: true, email: true }}
              autoComplete="username"
            />
            <Field
              id="oPass"
              name="pass"
              password
              label="Password"
              rule={{ required: true }}
              autoComplete="current-password"
            />
            {err && (
              <div className="form-err" id="oErr">
                {err}
              </div>
            )}
            <button className="btn wide" type="submit" disabled={busy}>
              Sign in
            </button>
          </ValidatedForm>
        )}
      </div>
      {!reg && (
        <div className="demo-acc">
          <span>
            Demo owner account: <code>nadia@lacvert.farm</code> / <code>demo1234</code>
          </span>
          <div className="row" style={{ justifyContent: 'flex-start' }}>
            <button className="small-btn" type="button" onClick={() => fill('nadia@lacvert.farm')}>
              Fill demo account
            </button>
          </div>
        </div>
      )}
      <p className="auth-switch">
        Work on a farm? <Link to="/worker-auth">Team sign in</Link>
      </p>
    </AuthLayout>
  );
}

export function TeamAuth() {
  const [err, setErr] = useState<ReactNode>(null);
  const [busy, setBusy] = useState(false);
  const { login } = useSession();
  const after = useAfterSignIn();
  const fill = useFill();
  useEffect(() => {
    window.setTimeout(() => {
      if (document.activeElement?.tagName === 'INPUT') return;
      (document.querySelector('#authCard input') as HTMLInputElement | null)?.focus({ preventScroll: true });
    }, 50);
  }, []);
  return (
    <AuthLayout
      quote={
        <>
          Your shift starts with the water, <em>not a guess.</em>
        </>
      }
    >
      <span className="pill">
        <i />
        Workers and technicians
      </span>
      <h1>Team sign in</h1>
      <p className="lead">
        Use the account your farm owner created for you. You'll see the pages they gave you access to.
      </p>
      <ValidatedForm
        onValid={async (d) => {
          setBusy(true);
          setErr(null);
          try {
            const me = await login('team', d.email.trim().toLowerCase(), d.pass);
            after(me.role);
          } catch (e) {
            if (e instanceof ApiError && e.code === 'wrong_portal')
              setErr(
                <>
                  This is an owner account. Use <Link to="/owner-auth">owner sign in</Link>.
                </>,
              );
            else setErr((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field
          id="tEmail"
          name="email"
          label="Work email"
          type="email"
          rule={{ required: true, email: true }}
          autoComplete="username"
        />
        <Field
          id="tPass"
          name="pass"
          password
          label="Password"
          rule={{ required: true }}
          autoComplete="current-password"
        />
        {err && (
          <div className="form-err" id="tErr">
            {err}
          </div>
        )}
        <button className="btn wide" type="submit" disabled={busy}>
          Sign in
        </button>
      </ValidatedForm>
      <div className="demo-acc">
        <span>
          Try a demo account (password <code>demo1234</code>)
        </span>
        <div className="row" style={{ justifyContent: 'flex-start' }}>
          <button className="small-btn" type="button" onClick={() => fill('karim@lacvert.farm')}>
            Worker · Karim
          </button>
          <button className="small-btn" type="button" onClick={() => fill('samir@lacvert.farm')}>
            Technician · Samir
          </button>
        </div>
      </div>
      <p className="auth-switch">
        Farm owner? <Link to="/owner-auth">Sign in or create your farm</Link>
      </p>
    </AuthLayout>
  );
}
