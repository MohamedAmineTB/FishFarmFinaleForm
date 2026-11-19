// App shell: white floating sidebar + topbar (simulator toggle, bell, assistant button).
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useLive } from '../api/realtime';
import { useSession } from '../api/session';
import { useAssistant } from '../assistant/context';
import { ROLE_LABEL, clock, hhmm, initials } from '../lib/format';
import { navItems } from '../lib/nav';
import { BrandSvg, Icon } from './Icons';
import { useToast } from './ui';

function FarmDots() {
  const { live } = useLive();
  if (!live) return <div className="farm-dots" id="farmDots" />;
  const need = live.basins.filter((b) => b.status !== 'healthy').length;
  const n = live.basins.length;
  return (
    <div className="farm-dots" id="farmDots">
      {live.basins.map((b) => (
        <i
          key={b.id}
          title={`${b.name}: ${b.status}`}
          style={{ background: b.status === 'critical' ? '#ff8f86' : b.status === 'warning' ? '#ffc96b' : '#7fe0b5' }}
        />
      ))}
      <span>{n === 0 ? 'no basins yet' : need ? `${need} of ${n} need attention` : 'all basins healthy'}</span>
    </div>
  );
}

function SimButton() {
  const { live, reload } = useLive();
  const { me } = useSession();
  const toast = useToast();
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const paused = !!live?.simulator.paused;
  const owner = me?.role === 'owner';
  return (
    <button
      className={`sim-btn${paused ? ' off' : ''}`}
      type="button"
      id="simBtn"
      title={owner ? 'Pause or resume the sensor simulator' : 'Sensor simulator (only the owner can pause it)'}
      aria-disabled={!owner}
      onClick={async () => {
        if (!owner) {
          toast(
            <>
              <b>Only the owner</b> can pause the simulator
            </>,
          );
          return;
        }
        await api(`/api/simulator/${paused ? 'resume' : 'pause'}`, { method: 'POST' });
        reload();
        toast(
          paused ? (
            <>
              <b>Simulator on</b> · sensors send readings again
            </>
          ) : (
            <>
              <b>Simulator paused</b> · readings frozen
            </>
          ),
        );
      }}
    >
      <i />
      <span id="clock">{paused ? 'paused' : `${clock(now)} · live`}</span>
    </button>
  );
}

function Bell({ alertsPath }: { alertsPath: string | null }) {
  const { live } = useLive();
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);
  const list = (live?.alerts ?? []).slice(0, 5);
  const n = live?.open_alerts ?? 0;
  return (
    <div ref={ref} style={{ display: 'contents' }}>
      <button
        className="icon-btn bell"
        type="button"
        id="bellBtn"
        aria-label="Notifications"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Icon name="alerts" size={19} />
        <span className="dot" id="bellDot">
          {n ? n : ''}
        </span>
      </button>
      <div className={`drop${open ? ' open' : ''}`} id="drop">
        <span className="hd">{list.length ? 'Open alerts' : 'No open alerts'}</span>
        {list.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => {
              setOpen(false);
              if (alertsPath) nav(alertsPath);
            }}
          >
            <b>
              {a.basin} · {a.title}
            </b>
            <span>
              {a.severity} · {hhmm(a.time)}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function Shell({ title, children }: { title: string; children: ReactNode }) {
  const { me, logout } = useSession();
  const { live } = useLive();
  const ai = useAssistant();
  const loc = useLocation();
  const nav = useNavigate();
  const toast = useToast();
  if (!me) return null;
  const items = navItems(me.role, me.permissions);
  const alertsItem = items.find((i) => i.key === 'alerts');
  const active = (path: string) => {
    if (path === loc.pathname) return true;
    if (loc.pathname.includes('/basins/'))
      return path.endsWith('/basins') || (path === '/worker' && me.role === 'worker');
    return false;
  };
  return (
    <div className="app" id="app" aria-label="FishFarm app">
      <aside className="side">
        <Link className="brand" to="/" aria-label="Back to the FishFarm website">
          <BrandSvg eye="#0c1d22" />
          fishfarm
        </Link>
        <div className="farm">
          <small>Farm</small>
          <strong id="farmName">{me.farm.name}</strong>
          <span className="role-chip" id="roleChip">
            {ROLE_LABEL[me.role]}
          </span>
          <FarmDots />
        </div>
        <span className="nav-label">Menu</span>
        <nav id="sideNav" aria-label="App">
          {items.map((it) => {
            const cnt = it.count === 'alerts' ? live?.open_alerts : it.count === 'reports' ? live?.unread_reports : 0;
            return (
              <button
                key={it.key}
                type="button"
                aria-current={active(it.path) ? 'page' : undefined}
                onClick={() => nav(it.path)}
              >
                <span className="lbl">
                  <Icon name={it.icon} size={17} />
                  {it.label}
                </span>
                {cnt ? (
                  <span className="count" style={it.count === 'reports' ? { background: 'var(--current)' } : undefined}>
                    {cnt}
                  </span>
                ) : null}
              </button>
            );
          })}
        </nav>
        <div className="side-foot">
          <div className="user-card">
            <span className={`avatar${me.role === 'technician' ? ' tech' : ''}`} id="meAv">
              {initials(me.user.name)}
            </span>
            <span className="who">
              <b id="meName">{me.user.name}</b>
              <span id="meEmail">{me.user.email}</span>
            </span>
            <button
              className="icon-btn"
              type="button"
              aria-label="Sign out"
              title="Sign out"
              onClick={async () => {
                const role = me.role;
                ai.close();
                await logout();
                toast(<b>Signed out</b>);
                nav(role === 'owner' ? '/owner-auth' : '/worker-auth');
              }}
            >
              <svg
                viewBox="0 0 24 24"
                width="18"
                height="18"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10" />
              </svg>
            </button>
          </div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div>
            <div className="crumbs" id="crumbs">
              {me.farm.name} · {ROLE_LABEL[me.role]}
            </div>
            <h1 id="viewTitle">{title}</h1>
          </div>
          <div className="top-acts">
            <SimButton />
            <Bell alertsPath={alertsItem?.path ?? null} />
            <button className="small-btn primary" type="button" onClick={() => ai.toggle()}>
              <svg
                viewBox="0 0 24 24"
                width="15"
                height="15"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M4 12c3-4.5 9-4.5 12 0-3 4.5-9 4.5-12 0z" />
                <path d="M16 12l4-3v6z" />
              </svg>
              <span className="ask-label">Ask the farm</span>
            </button>
          </div>
        </header>
        <main className="content" id="content">
          {children}
        </main>
      </div>
    </div>
  );
}
