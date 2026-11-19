import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, refreshToken, setToken } from './client';
import type { Me } from './types';
import { setFarmTz } from '../lib/format';

type State = { status: 'loading' | 'out' | 'in'; me: Me | null };

interface SessionApi extends State {
  login: (portal: 'owner' | 'team', email: string, password: string) => Promise<Me>;
  register: (body: Record<string, string>) => Promise<Me>;
  logout: () => Promise<void>;
  reloadMe: () => Promise<void>;
}

const Ctx = createContext<SessionApi | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: 'loading', me: null });

  const loadMe = useCallback(async () => {
    const me = await api<Me>('/api/me');
    setFarmTz(me.farm.timezone);
    setState({ status: 'in', me });
    return me;
  }, []);

  useEffect(() => {
    // restore the session after a page refresh from the httpOnly refresh cookie
    refreshToken().then((t) =>
      t ? loadMe().catch(() => setState({ status: 'out', me: null })) : setState({ status: 'out', me: null }),
    );
  }, [loadMe]);

  const value = useMemo<SessionApi>(
    () => ({
      ...state,
      async login(portal, email, password) {
        const r = await api<{ access_token: string }>('/api/auth/login', { body: { portal, email, password } });
        setToken(r.access_token);
        return loadMe();
      },
      async register(body) {
        const r = await api<{ access_token: string }>('/api/auth/register', { body });
        setToken(r.access_token);
        return loadMe();
      },
      async logout() {
        await api('/api/auth/logout', { method: 'POST' }).catch(() => undefined);
        setToken(null);
        setState({ status: 'out', me: null });
      },
      async reloadMe() {
        await loadMe().catch(() => undefined);
      },
    }),
    [state, loadMe],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession() {
  const c = useContext(Ctx);
  if (!c) throw new Error('SessionProvider missing');
  return c;
}
