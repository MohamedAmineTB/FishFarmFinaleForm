// Reports inbox (screens 18-20). Opening a report does not mark it read; the buttons do.
import { useState } from 'react';
import { api } from '../../api/client';
import { useApi, useLive } from '../../api/realtime';
import type { Report } from '../../api/types';
import { useTitle } from '../../App';
import { useEnter } from '../../components/Home';
import { Check, CheckSm } from '../../components/Icons';
import { Modal, useToast } from '../../components/ui';
import { fmtDate, fullDate, initials } from '../../lib/format';
import { LoadError } from './Overview';

export default function Reports() {
  useTitle('Reports inbox');
  const [tab, setTab] = useState<'all' | 'unread'>('all');
  const [openId, setOpenId] = useState<string | null>(null);
  const { data, error, setData } = useApi<Report[]>('/api/reports', ['report']);
  const { reload } = useLive();
  const toast = useToast();
  useEnter(!!data, 'reports');
  if (!data) return <LoadError error={error} />;
  const unread = data.filter((r) => !r.read).length;
  const shown = tab === 'unread' ? data.filter((r) => !r.read) : data;
  const open = data.find((r) => r.id === openId) ?? null;

  const toggle = async (r: Report, close?: boolean) => {
    const was = r.read;
    setData(data.map((x) => (x.id === r.id ? { ...x, read: !was } : x)));
    if (close) setOpenId(null);
    try {
      await api(`/api/reports/${r.id}/read`, { method: was ? 'DELETE' : 'POST' });
      toast(
        was ? (
          <b>Marked as unread</b>
        ) : (
          <>
            <b>Marked as read</b> · {r.title}
          </>
        ),
      );
    } catch (e) {
      setData(data);
      toast(<>{(e as Error).message}</>);
    }
    reload();
  };

  return (
    <>
      <div className="section-title">
        <p className="mini">Shift reports from workers and maintenance logs from technicians, newest first.</p>
        <div className="row">
          <div className="tabs" role="tablist" aria-label="Reports filter">
            <button role="tab" aria-selected={tab !== 'unread'} onClick={() => setTab('all')}>
              All · {data.length}
            </button>
            <button role="tab" aria-selected={tab === 'unread'} onClick={() => setTab('unread')}>
              Unread · {unread}
            </button>
          </div>
          {unread > 0 && (
            <button
              className="small-btn"
              onClick={async () => {
                setData(data.map((r) => ({ ...r, read: true })));
                await api('/api/reports/read-all', { method: 'POST' });
                toast(<b>All reports marked as read</b>);
                reload();
              }}
            >
              <CheckSm />
              Mark all as read
            </button>
          )}
        </div>
      </div>
      <div className="list">
        {shown.length ? (
          shown.map((r) => (
            <div className={`report${r.read ? ' is-read' : ''}`} key={r.id}>
              <button className="report-open" aria-label={`Open report: ${r.title}`} onClick={() => setOpenId(r.id)}>
                <div className="row">
                  <b>
                    {!r.read && <span className="unread" />}
                    {r.title}
                  </b>
                  <span className="mini mono">{fmtDate(r.time)}</span>
                </div>
                <span className="person">
                  <span className={`avatar${r.role === 'Technician' ? ' tech' : ''}`} style={{ width: 24, height: 24, fontSize: 10 }}>
                    {initials(r.author)}
                  </span>
                  <span className="mini">
                    {r.author} · <span className={`badge ${r.role === 'Worker' ? 'b-healthy' : 'b-info'}`}>{r.role}</span>
                  </span>
                </span>
                <p>{r.body}</p>
              </button>
              <button className={`read-btn${r.read ? ' on' : ''}`} aria-pressed={r.read} onClick={() => toggle(r)}>
                <CheckSm />
                {r.read ? 'Read' : 'Mark as read'}
              </button>
            </div>
          ))
        ) : (
          <div className="tile none">
            <span className="big-check">
              <Check />
            </span>
            <strong>{data.length ? "You're all caught up." : 'No reports yet.'}</strong>
            <span>{data.length ? 'Every report has been read.' : 'Shift reports and maintenance logs from your team appear here.'}</span>
          </div>
        )}
      </div>
      <Modal open={!!open} onClose={() => setOpenId(null)} label="Report">
        {open && (
          <>
            <span className="person">
              <span className={`avatar${open.role === 'Technician' ? ' tech' : ''}`}>{initials(open.author)}</span>
              <div>
                <b>{open.author}</b>
                <span>
                  {open.role} · {fullDate(open.time)}
                </span>
              </div>
            </span>
            <h3>{open.title}</h3>
            <p style={{ fontSize: 14.5, lineHeight: 1.6 }}>{open.body}</p>
            <div className="acts-row">
              <button className="small-btn" onClick={() => setOpenId(null)}>
                Close
              </button>
              {open.read ? (
                <button className="small-btn" onClick={() => toggle(open, true)}>
                  Mark as unread
                </button>
              ) : (
                <button className="small-btn ok" onClick={() => toggle(open, true)}>
                  <CheckSm />
                  Mark as read
                </button>
              )}
            </div>
          </>
        )}
      </Modal>
    </>
  );
}
