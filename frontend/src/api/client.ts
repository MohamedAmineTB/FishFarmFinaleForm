// API client: the access token lives in memory only; the refresh token is an httpOnly cookie
// the browser sends to /api/auth/refresh. A 401 triggers one silent refresh, then a retry.

let accessToken: string | null = null;
let refreshing: Promise<string | null> | null = null;
const listeners = new Set<(token: string | null) => void>();

export class ApiError extends Error {
  status: number;
  code?: string;
  detail: any;
  constructor(status: number, detail: any) {
    const msg =
      typeof detail === 'string'
        ? detail
        : detail?.message || (Array.isArray(detail) ? 'Check the highlighted fields.' : 'Something went wrong.');
    super(msg);
    this.status = status;
    this.detail = detail;
    this.code = typeof detail === 'object' && detail ? detail.code : undefined;
  }
}

export function getToken() {
  return accessToken;
}

export function setToken(t: string | null) {
  accessToken = t;
  listeners.forEach((l) => l(t));
}

export function onToken(l: (t: string | null) => void) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export async function refreshToken(): Promise<string | null> {
  if (!refreshing) {
    refreshing = fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' })
      .then(async (r) => (r.ok ? ((await r.json()).access_token as string) : null))
      .catch(() => null)
      .then((t) => {
        setToken(t);
        refreshing = null;
        return t;
      });
  }
  return refreshing;
}

async function parse(r: Response) {
  const text = await r.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

export async function api<T = any>(
  path: string,
  opts: { method?: string; body?: unknown; retry?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const r = await fetch(path, {
    method: opts.method ?? (opts.body !== undefined ? 'POST' : 'GET'),
    headers,
    credentials: 'include',
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (r.status === 401 && opts.retry !== false && !path.startsWith('/api/auth/')) {
    const t = await refreshToken();
    if (t) return api<T>(path, { ...opts, retry: false });
  }
  const data = await parse(r);
  if (!r.ok) throw new ApiError(r.status, data?.detail ?? data);
  return data as T;
}
