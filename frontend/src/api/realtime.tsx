import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { api, getToken, onToken, refreshToken } from './client';
import type { Live } from './types';
import { useSession } from './session';

export type FarmEvent = { type: string; [k: string]: any };
type Listener = (e: FarmEvent) => void;

const bus = new Set<Listener>();
export function subscribe(l: Listener) {
  bus.add(l);
  return () => {
    bus.delete(l);
  };
}
function emit(e: FarmEvent) {
  bus.forEach((l) => l(e));
}

/** One WebSocket per signed-in tab; reconnects with back-off and a fresh token. */
function useSocket(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    let ws: WebSocket | null = null;
    let stop = false;
    let wait = 1000;
    let ping: number | undefined;
    let timer: number | undefined;
    const connect = async () => {
      let token = getToken();
      if (!token) token = await refreshToken();
      if (!token || stop) return;
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(token)}`);
      ws.onopen = () => {
        wait = 1000;
        emit({ type: 'connected' });
        ping = window.setInterval(() => ws?.readyState === 1 && ws.send('ping'), 25000);
      };
      ws.onmessage = (m) => {
        try {
          emit(JSON.parse(m.data));
        } catch {
          /* ignore */
        }
      };
      ws.onclose = async (ev) => {
        window.clearInterval(ping);
        if (stop) return;
        if (ev.code === 4401) await refreshToken();
        timer = window.setTimeout(connect, wait);
        wait = Math.min(wait * 2, 15000);
      };
    };
    connect();
    const off = onToken((t) => {
      if (!t) ws?.close();
    });
    return () => {
      stop = true;
      off();
      window.clearInterval(ping);
      window.clearTimeout(timer);
      ws?.close();
    };
  }, [enabled]);
}

interface LiveApi {
  live: Live | null;
  reload: () => void;
}
const LiveCtx = createContext<LiveApi>({ live: null, reload: () => undefined });

const LIVE_EVENTS = new Set(['readings', 'alert', 'report', 'sensor_health', 'simulator', 'farm', 'connected', 'task']);

export function LiveProvider({ children }: { children: ReactNode }) {
  const { status, me, reloadMe } = useSession();
  const [live, setLive] = useState<Live | null>(null);
  const inFlight = useRef(false);
  const again = useRef(false);
  const signedIn = status === 'in';
  useSocket(signedIn);

  const reload = useCallback(() => {
    if (inFlight.current) {
      again.current = true;
      return;
    }
    inFlight.current = true;
    api<Live>('/api/live')
      .then(setLive)
      .catch(() => undefined)
      .finally(() => {
        inFlight.current = false;
        if (again.current) {
          again.current = false;
          reload();
        }
      });
  }, []);

  useEffect(() => {
    if (!signedIn) {
      setLive(null);
      return;
    }
    reload();
    return subscribe((e) => {
      if (LIVE_EVENTS.has(e.type)) reload();
      // permissions are pushed live: the member's menu updates without a refresh
      if (e.type === 'permissions' && me && e.user_id === me.user.id) reloadMe();
    });
  }, [signedIn, reload, me, reloadMe]);

  return <LiveCtx.Provider value={{ live, reload }}>{children}</LiveCtx.Provider>;
}

export function useLive() {
  return useContext(LiveCtx);
}

/** Fetch JSON and refetch when one of the given event types arrives. */
export function useApi<T>(path: string | null, refreshOn: string[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(!!path);
  const key = refreshOn.join(',');
  const load = useCallback(() => {
    if (!path) return Promise.resolve();
    return api<T>(path)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e))
      .finally(() => setLoading(false));
  }, [path]);
  useEffect(() => {
    setLoading(!!path);
    load();
  }, [load, path]);
  useEffect(() => {
    if (!key) return;
    const types = new Set(key.split(','));
    let t: number | undefined;
    const off = subscribe((e) => {
      if (types.has(e.type)) {
        window.clearTimeout(t);
        t = window.setTimeout(load, 250);
      }
    });
    return () => {
      off();
      window.clearTimeout(t);
    };
  }, [key, load]);
  return { data, error, loading, reload: load, setData };
}
