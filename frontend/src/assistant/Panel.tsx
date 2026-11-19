// Farm assistant panel (screens 25, 26, 54): right drawer, streamed answers with tool steps,
// charts, risk cards, comparisons, sources, data used, approval cards, feedback and follow-ups.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { api, getToken, refreshToken } from '../api/client';
import { useLive } from '../api/realtime';
import { useSession } from '../api/session';
import type { Basin, Metric } from '../api/types';
import { LineChart, basinChartProps } from '../components/Charts';
import { useToast } from '../components/ui';
import { clamp, fmtDate } from '../lib/format';
import { AssistantCtx } from './context';

type Ev = { type: string; [k: string]: any };
interface Step {
  id: string;
  label: string;
  done: boolean;
  ok: boolean;
}
interface Turn {
  q: string;
  steps: Step[];
  text: string;
  ui: Ev[];
  approvals: (Ev & { status?: string; result?: string })[];
  followups: string[];
  error?: string;
  messageId?: string;
  rating?: number | null;
  done: boolean;
  dir?: 'rtl' | 'ltr';
  data: { name: string; args: unknown }[];
}

const esc = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
/** Tiny safe markdown (ported from the prototype): escape first, then paragraphs, lists and **bold**. Never raw HTML. */
export function md(t: string) {
  return esc(t)
    .split(/\n\n+/)
    .map((block) => {
      const lines = block.split('\n');
      if (lines.every((l) => /^- /.test(l)))
        return '<ul>' + lines.map((l) => '<li>' + l.slice(2) + '</li>').join('') + '</ul>';
      if (lines.every((l) => /^\d+\. /.test(l)))
        return '<ol>' + lines.map((l) => '<li>' + l.replace(/^\d+\. /, '') + '</li>').join('') + '</ol>';
      return '<p>' + block.replace(/\n/g, '<br>') + '</p>';
    })
    .join('')
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
}

/** 'UF/IFAS Extension (EDIS FA002)' -> 'UF/IFAS FA002', 'Southern Regional Aquaculture Center (SRAC)' -> 'SRAC' */
export function shortPublisher(p: string) {
  const inner = p.match(/\(([^)]+)\)/)?.[1];
  if (inner && /^[A-Z]{2,6}$/.test(inner)) return inner;
  if (inner?.startsWith('EDIS ')) return p.split(' ')[0] + ' ' + inner.slice(5);
  return p.split(' (')[0];
}

function chipsFor(role: string, page: string, basin?: string) {
  if (role === 'technician')
    return ['Is the Basin 4 alert a sensor problem?', 'Which sensors need calibration?', 'Summarize open alerts'];
  if (role === 'worker')
    return [
      'What should I do first on this shift?',
      'Why did oxygen drop in Basin 3 last night?',
      'Summarize open alerts',
    ];
  if (page === 'basin' && basin)
    return [
      `Why did oxygen drop in ${basin} last night?`,
      `What if I add 500 fish to ${basin}?`,
      'What is my risk today?',
    ];
  if (page === 'alerts')
    return [
      "Summarize today's critical alerts",
      'Is the Basin 4 alert a sensor problem?',
      'Why did oxygen drop in Basin 3 last night?',
    ];
  return [
    'What needs my attention today?',
    'Why did oxygen drop in Basin 3 last night?',
    'How can I raise revenue?',
    'What is my risk today?',
    'Give me 3 actions for this week',
    'Compare margin per basin this quarter',
  ];
}

async function* sse(body: unknown, signal: AbortSignal): AsyncGenerator<Ev> {
  let token = getToken() ?? (await refreshToken());
  let r = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
    signal,
    credentials: 'include',
  });
  if (r.status === 401) {
    token = await refreshToken();
    r = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
      signal,
      credentials: 'include',
    });
  }
  if (!r.ok || !r.body) {
    yield {
      type: 'error',
      message:
        r.status === 422
          ? 'Please keep questions under 2,000 characters.'
          : 'The assistant is unavailable right now. Try again in a moment.',
    };
    return;
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf = (buf + dec.decode(value, { stream: true })).replace(/\r\n/g, '\n');
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const data = chunk
        .split('\n')
        .filter((l) => l.startsWith('data:'))
        .map((l) => l.slice(5).trimStart())
        .join('\n');
      if (data) {
        try {
          yield JSON.parse(data);
        } catch {
          /* keep-alive */
        }
      }
    }
  }
}

function AiChart({ ev, basins }: { ev: Ev; basins: Basin[] }) {
  const b = basins.find((x) => x.id === ev.basin_id || x.name === ev.basin);
  if (!b || !ev.values?.length) return null;
  const props = basinChartProps(b, ev.metric as Metric, { times: ev.times, values: ev.values }, 190);
  return (
    <div className="chart">
      <LineChart {...props} />
    </div>
  );
}

function TurnView({
  t,
  basins,
  onAsk,
  onApprove,
  onCancel,
  onRate,
}: {
  t: Turn;
  basins: Basin[];
  onAsk: (q: string) => void;
  onApprove: (id: string) => void;
  onCancel: (id: string) => void;
  onRate: (r: number, reason?: string) => void;
}) {
  const [reasonOpen, setReasonOpen] = useState(false);
  const [reason, setReason] = useState('');
  const sources = t.ui.filter((u) => u.type === 'source');
  return (
    <>
      <div className="msg-user" dir={t.dir}>
        {t.q}
      </div>
      <div className="msg-ai" dir={t.dir}>
        {t.steps.length > 0 && (
          <div className="steps">
            {t.steps.map((s) => (
              <span className="stepchip" key={s.id}>
                {s.done ? <span className="ok">{s.ok ? '✓' : '!'}</span> : <span className="spin" />}
                {s.label}
              </span>
            ))}
          </div>
        )}
        {t.text && <div dangerouslySetInnerHTML={{ __html: md(t.text) }} />}
        {t.error && <div className="ai-err">{t.error}</div>}
        {t.ui.map((u, i) =>
          u.type === 'chart' ? (
            <AiChart key={i} ev={u} basins={basins} />
          ) : u.type === 'risk' ? (
            <div className="risk-cards" key={i}>
              {u.cards.map((r: any) => (
                <div key={r.name}>
                  <b>
                    {r.name} <span className="mini">{r.species}</span>
                  </b>
                  <span className={`badge ${r.p > 0.5 ? 'b-critical' : r.p > 0.2 ? 'b-warning' : 'b-healthy'}`}>
                    {r.p > 0.5 ? 'High' : r.p > 0.2 ? 'Medium' : 'Low'} · {Math.round(r.p * 100)}%
                  </span>
                  <span className="mini" style={{ gridColumn: '1/-1' }}>
                    {r.why} · estimate
                  </span>
                  <div className="risk-meter">
                    <i
                      style={{
                        width: `${Math.round(r.p * 100)}%`,
                        background: r.p > 0.5 ? 'var(--crit)' : r.p > 0.2 ? 'var(--warn)' : 'var(--ok)',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : u.type === 'compare' ? (
            <div className="cmp" key={i}>
              {u.rows.map((c: any) => (
                <div key={c.name}>
                  <span>{c.name}</span>
                  <i style={{ width: `${clamp(Math.round(c.v * 100), 2, 100)}%` }} />
                  <span className="mono">{c.raw}</span>
                </div>
              ))}
            </div>
          ) : null,
        )}
        {sources.length > 0 && (
          <div className="srcs">
            {sources.map((s, i) =>
              s.url ? (
                <a
                  className="src"
                  key={i}
                  href={s.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  title={`${s.publisher}${s.year ? ', ' + s.year : ''}`}
                >
                  {s.publisher ? `${shortPublisher(s.publisher)} · ${s.title}` : s.title}
                </a>
              ) : (
                <span className="src" key={i}>
                  {s.title}
                </span>
              ),
            )}
          </div>
        )}
        {t.data.length > 0 && (
          <details className="data-used">
            <summary>
              Data used · {t.data.length} tool call{t.data.length > 1 ? 's' : ''}
            </summary>
            <pre>
              {t.data
                .map(
                  (d) =>
                    `${d.name}(${Object.entries((d.args as Record<string, unknown>) || {})
                      .map(([k, v]) => `${k}=${v}`)
                      .join(', ')})`,
                )
                .join('\n')}
              {'\n'}owner scope: set by the server from your login
            </pre>
          </details>
        )}
        {t.approvals.map((a) => (
          <div className={`approve${a.status === 'approved' ? ' done' : ''}`} key={a.id}>
            {a.status === 'approved' ? (
              <span className="mini">
                ✓ Task created
                {a.assignee_name ? (
                  <>
                    {' '}
                    and assigned to <b>{a.assignee_name}</b>
                  </>
                ) : null}
                . You'll find it under Maintenance.
              </span>
            ) : a.status === 'cancelled' ? (
              <span className="mini">No task created.</span>
            ) : (
              <>
                <span className="mini">
                  {a.tool === 'acknowledge_alert' ? 'Suggested action: ' : 'Suggested task: '}
                  <b>{a.title ?? a.note}</b>
                  {a.assignee_name ? ` · assign to ${a.assignee_name}` : ''}
                  {a.due ? ` · ${a.due}` : ''}
                </span>
                <div className="row" style={{ justifyContent: 'flex-start' }}>
                  <button className="small-btn primary" type="button" onClick={() => onApprove(a.id)}>
                    Approve and create task
                  </button>
                  <button className="small-btn" type="button" onClick={() => onCancel(a.id)}>
                    Not now
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
        {t.done && t.messageId && !t.error && (
          <div className="fb">
            Was this useful?
            <button type="button" aria-pressed={t.rating === 1} aria-label="Useful" onClick={() => onRate(1)}>
              👍
            </button>
            <button
              type="button"
              aria-pressed={t.rating === -1}
              aria-label="Not useful"
              onClick={() => {
                onRate(-1);
                setReasonOpen(true);
              }}
            >
              👎
            </button>
          </div>
        )}
        {reasonOpen && (
          <form
            className="fb-reason"
            onSubmit={(e) => {
              e.preventDefault();
              onRate(-1, reason.trim() || undefined);
              setReasonOpen(false);
            }}
          >
            <label htmlFor={`why-${t.messageId}`} className="mini" style={{ position: 'absolute', left: -9999 }}>
              What was wrong?
            </label>
            <input
              id={`why-${t.messageId}`}
              placeholder="What was wrong? (optional)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={500}
            />
            <button className="small-btn" type="submit">
              Send
            </button>
          </form>
        )}
        {t.followups.length > 0 && (
          <div className="chips">
            {t.followups.map((f) => (
              <button className="chip" type="button" key={f} onClick={() => onAsk(f)}>
                {f}
              </button>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

const SR: any =
  typeof window !== 'undefined' ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null;

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [convId, setConvId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState('');
  const [history, setHistory] = useState<{ id: string; title: string; updated_at: string }[]>([]);
  const [listening, setListening] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const body = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { me } = useSession();
  const { live } = useLive();
  const loc = useLocation();
  const toast = useToast();
  const basins = useMemo(() => live?.basins ?? [], [live]);

  // page-aware context: which page and which basin the user is looking at
  const page = useMemo(() => {
    const m = loc.pathname.match(/\/basins\/([0-9a-f-]+)/);
    const b = m ? basins.find((x) => x.id === m[1]) : undefined;
    const name = loc.pathname.split('/')[2] || 'home';
    return { page: b ? 'basin' : name === 'alerts' ? 'alerts' : name, basin: b?.name };
  }, [loc.pathname, basins]);

  const scroll = () =>
    window.requestAnimationFrame(() => body.current && (body.current.scrollTop = body.current.scrollHeight));
  const patch = (fn: (t: Turn) => Turn) => setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? fn(t) : t)));

  const ask = useCallback(
    async (q: string) => {
      q = (q || '').trim().slice(0, 4000);
      if (!q || busy) return;
      setOpen(true);
      setBusy(true);
      const ctrl = new AbortController();
      abort.current = ctrl;
      setTurns((ts) => [
        ...ts,
        { q, steps: [], text: '', ui: [], approvals: [], followups: [], done: false, data: [] },
      ]);
      scroll();
      try {
        for await (const ev of sse({ message: q, conversation_id: convId, page }, ctrl.signal)) {
          if (ev.type === 'meta') {
            setConvId(ev.conversation_id);
            patch((t) => ({ ...t, dir: ev.dir }));
          } else if (ev.type === 'token') patch((t) => ({ ...t, text: t.text + ev.text }));
          else if (ev.type === 'tool_call')
            patch((t) => ({
              ...t,
              steps: [...t.steps, { id: ev.id, label: ev.label, done: false, ok: true }],
              data: [...t.data, { name: ev.name, args: ev.args }],
            }));
          else if (ev.type === 'tool_result')
            patch((t) => ({ ...t, steps: t.steps.map((s) => (s.id === ev.id ? { ...s, done: true, ok: ev.ok } : s)) }));
          else if (['chart', 'risk', 'compare', 'source'].includes(ev.type))
            patch((t) => ({ ...t, ui: [...t.ui, ev] }));
          else if (ev.type === 'approval_request') patch((t) => ({ ...t, approvals: [...t.approvals, ev] }));
          else if (ev.type === 'followups') patch((t) => ({ ...t, followups: ev.items }));
          else if (ev.type === 'error') patch((t) => ({ ...t, error: ev.message }));
          else if (ev.type === 'done') patch((t) => ({ ...t, done: true, messageId: ev.message_id }));
          scroll();
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError')
          patch((t) => ({ ...t, error: 'The connection was interrupted. Try again.' }));
        else patch((t) => ({ ...t, error: 'Stopped.' }));
      } finally {
        patch((t) => ({ ...t, done: true, steps: t.steps.map((s) => ({ ...s, done: true })) }));
        setBusy(false);
        abort.current = null;
        scroll();
      }
    },
    [busy, convId, page],
  );

  const reset = useCallback(() => {
    if (busy) return;
    setTurns([]);
    setConvId(null);
    api<typeof history>('/api/chat/conversations')
      .then(setHistory)
      .catch(() => undefined);
  }, [busy]);

  const loadConversation = async (id: string) => {
    const msgs = await api<any[]>(`/api/chat/conversations/${id}`);
    const out: Turn[] = [];
    for (const m of msgs) {
      if (m.role === 'user')
        out.push({
          q: m.content.text,
          steps: [],
          text: '',
          ui: [],
          approvals: [],
          followups: [],
          done: true,
          data: [],
        });
      else if (out.length) {
        const c = m.content;
        const t = out[out.length - 1];
        t.text = c.text;
        t.ui = (c.ui || []).filter((u: Ev) => u.type !== 'data');
        t.data = (c.ui || []).filter((u: Ev) => u.type === 'data');
        t.steps = t.data.map((d, i) => ({ id: String(i), label: d.name.replace(/_/g, ' '), done: true, ok: true }));
        t.approvals = c.approvals || [];
        t.followups = c.followups || [];
        t.messageId = m.id;
        t.rating = m.rating;
        t.dir = c.lang === 'ar' ? 'rtl' : 'ltr';
      }
    }
    setTurns(out);
    setConvId(id);
    scroll();
  };

  // open from anywhere; "Ask it in the demo" on the website arrives as navigation state
  useEffect(() => {
    const st = loc.state as { ask?: string } | null;
    if (st?.ask) {
      const q = st.ask;
      window.history.replaceState({}, '');
      window.setTimeout(() => ask(q), 450);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!isOpen) return;
    if (!turns.length)
      api<typeof history>('/api/chat/conversations')
        .then(setHistory)
        .catch(() => undefined);
    window.setTimeout(() => inputRef.current?.focus({ preventScroll: true }), 300);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('keydown', esc);
    return () => document.removeEventListener('keydown', esc);
  }, [isOpen, turns.length]);

  const value = useMemo(
    () => ({ isOpen, open: () => setOpen(true), close: () => setOpen(false), toggle: () => setOpen((o) => !o), ask }),
    [isOpen, ask],
  );

  const critical = basins.filter((b) => b.status === 'critical');
  const demo = me?.assistant.demo_mode;

  const decide = async (id: string, decision: 'approve' | 'cancel') => {
    try {
      const r = await api<{ status: string; assignee?: string }>(`/api/chat/actions/${id}/${decision}`, {
        method: 'POST',
      });
      setTurns((ts) =>
        ts.map((t) => ({ ...t, approvals: t.approvals.map((a) => (a.id === id ? { ...a, status: r.status } : a)) })),
      );
      if (decision === 'approve') {
        const a = turns.flatMap((t) => t.approvals).find((x) => x.id === id);
        toast(
          <>
            <b>Task created</b> · {a?.title ?? ''}
          </>,
        );
      }
    } catch (e) {
      toast(<>{(e as Error).message}</>);
    }
  };

  const voice = () => {
    if (!SR) return;
    const rec = new SR();
    rec.lang = document.documentElement.lang === 'fr' ? 'fr-FR' : navigator.language || 'en-GB';
    rec.interimResults = false;
    rec.onresult = (e: any) => setInput((v) => (v ? v + ' ' : '') + e.results[0][0].transcript);
    rec.onend = () => setListening(false);
    setListening(true);
    rec.start();
  };

  return (
    <AssistantCtx.Provider value={value}>
      {children}
      <aside
        className={`panel-ai${isOpen ? ' open' : ''}`}
        id="aiPanel"
        aria-label="Farm assistant"
        aria-hidden={!isOpen}
      >
        <div className="ai-head">
          <b>Farm assistant</b>
          <div className="acts">
            {turns.length > 0 && (
              <button
                className="small-btn"
                type="button"
                onClick={() => window.print()}
                title="Save this conversation as a PDF"
              >
                PDF
              </button>
            )}
            <button className="small-btn" type="button" id="aiNew" onClick={reset}>
              New chat
            </button>
            <button
              className="small-btn"
              type="button"
              id="aiClose"
              aria-label="Close assistant"
              onClick={() => setOpen(false)}
            >
              ✕
            </button>
          </div>
        </div>
        {demo && (
          <div className="demo-banner">
            Demo mode: answers are built from the farm's live data with prepared templates. Add an API key in the real
            app for free-form answers.
          </div>
        )}
        {critical.length > 0 && (
          <div className="emergency" role="alert">
            <b>Emergency · {critical.map((b) => b.name).join(', ')} is critical</b>
            <ol>
              <li>Stop feeding for 1 to 3 days.</li>
              <li>Run the aerators until after sunrise.</li>
              <li>Exchange 25–50 % of the water if you can.</li>
              <li>If the reading looks impossible, call the technician: it may be the probe.</li>
            </ol>
            <span className="mini">
              Sources: UF/IFAS FA002 · SRAC pond aeration. The alert itself comes from the alert engine.
            </span>
          </div>
        )}
        <div className="ai-body" id="aiBody" ref={body}>
          {turns.length === 0 ? (
            <div className="ai-empty">
              <strong>Ask your farm.</strong>
              <span>
                I read the live readings, alerts, costs and the oxygen prediction for your basins, check the safe range
                for each species, and answer with numbers and sources. I ask before I create any task. I can't control
                equipment, and alerts always come from the alert engine.
              </span>
              <div className="chips">
                {chipsFor(me?.role ?? 'owner', page.page, page.basin).map((q) => (
                  <button className="chip" type="button" key={q} onClick={() => ask(q)}>
                    {q}
                  </button>
                ))}
              </div>
              {history.length > 0 && (
                <div className="ai-hist">
                  <span className="mini">Recent conversations</span>
                  {history.slice(0, 5).map((h) => (
                    <button type="button" key={h.id} onClick={() => loadConversation(h.id)}>
                      {h.title}
                      <span>{fmtDate(h.updated_at)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            turns.map((t, i) => (
              <TurnView
                key={i}
                t={t}
                basins={basins}
                onAsk={ask}
                onApprove={(id) => decide(id, 'approve')}
                onCancel={(id) => decide(id, 'cancel')}
                onRate={async (r, reason) => {
                  setTurns((ts) => ts.map((x, k) => (k === i ? { ...x, rating: r } : x)));
                  await api('/api/chat/feedback', { body: { message_id: t.messageId, rating: r, reason } }).catch(
                    () => undefined,
                  );
                  if (reason || r === 1)
                    toast(
                      <>
                        <b>Thanks</b> · feedback saved for the AI Ops review
                      </>,
                    );
                }}
              />
            ))
          )}
        </div>
        <form
          className="ai-input"
          id="aiForm"
          onSubmit={(e) => {
            e.preventDefault();
            const q = input;
            setInput('');
            ask(q);
          }}
        >
          <label htmlFor="aiText" className="mini" style={{ position: 'absolute', left: -9999 }}>
            Ask a question
          </label>
          <input
            id="aiText"
            ref={inputRef}
            autoComplete="off"
            maxLength={2000}
            placeholder="Ask about a basin, an alert or your costs"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          {SR && !busy && (
            <button
              className="small-btn"
              type="button"
              onClick={voice}
              aria-label="Speak your question"
              aria-pressed={listening}
            >
              {listening ? '…' : '🎤'}
            </button>
          )}
          {busy ? (
            <button className="small-btn stop" type="button" onClick={() => abort.current?.abort()}>
              Stop
            </button>
          ) : (
            <button className="small-btn primary" type="submit">
              Send
            </button>
          )}
        </form>
      </aside>
    </AssistantCtx.Provider>
  );
}
