import { createContext, lazy, Suspense, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { LiveProvider } from './api/realtime';
import { SessionProvider, useSession } from './api/session';
import type { Perms, Role } from './api/types';
import { AssistantProvider } from './assistant/Panel';
import { Shell } from './components/Shell';
import { ToastProvider, useToast } from './components/ui';
import { authPath, homePath } from './lib/nav';
import Landing from './pages/site/Landing';
import { OwnerAuth, TeamAuth } from './pages/auth/Auth';
import Overview from './pages/owner/Overview';
import Basins from './pages/owner/Basins';
import BasinDetail from './pages/owner/BasinDetail';
import Alerts from './pages/owner/Alerts';
import Reports from './pages/owner/Reports';
import Team from './pages/owner/Team';
import WorkerToday from './pages/worker/Today';
import ShiftReport from './pages/worker/ShiftReport';
import TechToday from './pages/tech/Today';
import SensorHealth from './pages/tech/SensorHealth';
import Maintenance from './pages/tech/Maintenance';
import NoPages from './pages/worker/NoPages';

const AiOps = lazy(() => import('./pages/owner/AiOps'));

/* ---------- page title (topbar) ---------- */
const TitleCtx = createContext<(t: string) => void>(() => undefined);
export function useTitle(t: string) {
  const set = useContext(TitleCtx);
  useEffect(() => set(t), [set, t]);
}

/* ---------- html classes: in-app / in-auth ---------- */
export function useHtmlMode(mode: 'app' | 'auth' | 'site') {
  useEffect(() => {
    const c = document.documentElement.classList;
    c.toggle('in-app', mode === 'app');
    c.toggle('in-auth', mode === 'auth');
    return () => {
      c.remove('in-app', 'in-auth');
    };
  }, [mode]);
}

function AppLayout({ role }: { role: Role }) {
  const { status, me } = useSession();
  const toast = useToast();
  const loc = useLocation();
  const warned = useRef(false);
  const [title, setTitle] = useState('');
  useHtmlMode('app');
  const out = status === 'out';
  useEffect(() => {
    if (out && !warned.current) {
      warned.current = true;
      toast(
        <>
          <b>Sign in</b> to open this page
        </>,
      );
    }
  }, [out, toast]);
  if (status === 'loading') return null;
  if (out || !me) return <Navigate to={authPath(role)} replace state={{ from: loc.pathname }} />;
  if (me.role !== role) return <Navigate to={homePath(me.role)} replace />;
  return (
    <TitleCtx.Provider value={setTitle}>
      <AssistantProvider>
        <Shell title={title}>
          <Suspense fallback={null}>
            <Outlet />
          </Suspense>
        </Shell>
      </AssistantProvider>
    </TitleCtx.Provider>
  );
}

/** Pages a team member only sees when the owner switched the permission on (checked by the API too). */
function Need({ perm, children }: { perm: keyof Perms; children: ReactNode }) {
  const { me } = useSession();
  if (!me) return null;
  if (me.role !== 'owner' && !me.permissions[perm]) return <Navigate to={homePath(me.role)} replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <SessionProvider>
          <LiveProvider>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/owner-auth" element={<OwnerAuth />} />
              <Route path="/worker-auth" element={<TeamAuth />} />
              <Route path="/owner" element={<AppLayout role="owner" />}>
                <Route index element={<Overview />} />
                <Route path="basins" element={<Basins />} />
                <Route path="basins/:id" element={<BasinDetail />} />
                <Route path="alerts" element={<Alerts />} />
                <Route path="reports" element={<Reports />} />
                <Route path="team" element={<Team />} />
                <Route path="ai-ops" element={<AiOps />} />
              </Route>
              <Route path="/worker" element={<AppLayout role="worker" />}>
                <Route index element={<WorkerToday />} />
                <Route path="alerts" element={<Need perm="alerts"><Alerts /></Need>} />
                <Route path="report" element={<Need perm="reports"><ShiftReport /></Need>} />
                <Route path="sensors" element={<Need perm="sensors"><SensorHealth /></Need>} />
                <Route path="maintenance" element={<Need perm="maintenance"><Maintenance /></Need>} />
                <Route path="basins/:id" element={<Need perm="basins"><BasinDetail /></Need>} />
                <Route path="none" element={<NoPages />} />
              </Route>
              <Route path="/technician" element={<AppLayout role="technician" />}>
                <Route index element={<TechToday />} />
                <Route path="alerts" element={<Need perm="alerts"><Alerts /></Need>} />
                <Route path="sensors" element={<Need perm="sensors"><SensorHealth /></Need>} />
                <Route path="maintenance" element={<Need perm="maintenance"><Maintenance /></Need>} />
                <Route path="basins" element={<Need perm="basins"><Basins /></Need>} />
                <Route path="basins/:id" element={<Need perm="basins"><BasinDetail /></Need>} />
                <Route path="report" element={<Need perm="reports"><ShiftReport /></Need>} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </LiveProvider>
        </SessionProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
