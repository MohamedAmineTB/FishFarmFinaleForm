// Home-screen building blocks shared by the owner, worker and technician (same language as the website).
import gsap from 'gsap';
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { eur } from '../lib/format';
import { WaterCanvas, reduceMotion } from './Water';

/** Wraps every word in a span.w (the prototype's splitEl) so headlines can be revealed word by word. */
export function Words({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\s+)/).map((p, i) =>
        !p ? null : /^\s+$/.test(p) ? (
          p
        ) : (
          <span className="w" key={i}>
            {p}
          </span>
        ),
      )}
    </>
  );
}

export function HomeHero({ eyebrow, title, text, ctas, progress }: { eyebrow: string; title: ReactNode; text: ReactNode; ctas: ReactNode; progress?: number | null }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useLayoutEffect(() => {
    if (reduceMotion() || !ref.current) return;
    const ctx = gsap.context(() => {
      gsap.from(ref.current!.querySelectorAll('.w'), { opacity: 0, y: 24, filter: 'blur(10px)', duration: 1, stagger: 0.06, ease: 'power3.out', clearProps: 'filter' });
    });
    return () => ctx.revert();
  }, []);
  return (
    <section className="home-hero">
      <div className="home-media">
        <WaterCanvas id="ovCanvas" opts={{ palette: 'light', fish: 24, top: 0.2 }} />
      </div>
      <div className="home-copy">
        <span className="eyebrow">{eyebrow}</span>
        <h2 id="homeTitle" ref={ref}>
          {title}
        </h2>
        <p>{text}</p>
        <div className="hero-ctas">{ctas}</div>
        {progress != null && (
          <div className="shift-bar light" aria-label={`Shift ${progress}% done`}>
            <i style={{ width: progress + '%' }} />
          </div>
        )}
      </div>
    </section>
  );
}

export function Ticket({ label, value, note, alert }: { label: string; value: ReactNode; note: ReactNode; alert?: boolean }) {
  return (
    <div className={`card${alert ? ' alert-card' : ''}`}>
      <small>{label}</small>
      <b>{value}</b>
      <span className="note">{note}</span>
    </div>
  );
}

export function Tickets({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (reduceMotion() || !ref.current) return;
    const ctx = gsap.context(() => {
      gsap.from(ref.current!.querySelectorAll('.card'), { y: 40, opacity: 0, duration: 0.9, stagger: 0.08, ease: 'power3.out', delay: 0.2, clearProps: 'opacity,transform' });
    });
    return () => ctx.revert();
  }, []);
  return (
    <div className="tickets" ref={ref}>
      {children}
    </div>
  );
}

/** Number that counts up once on first render (like the prototype's data-countup). */
export function CountUp({ value, kind = 'int' }: { value: number; kind?: 'int' | 'eur' }) {
  const format = (v: number) => (kind === 'eur' ? eur(v) : Math.round(v).toLocaleString('en-US'));
  const [shown, setShown] = useState(() => (reduceMotion() ? value : 0));
  const started = useRef(false);
  useEffect(() => {
    if (reduceMotion() || started.current) {
      setShown(value);
      return;
    }
    started.current = true;
    const o = { v: 0 };
    const tw = gsap.to(o, { v: value, duration: 1.1, ease: 'power2.out', onUpdate: () => setShown(o.v) });
    return () => {
      tw.progress(1);
      tw.kill();
    };
  }, [value]);
  return <span>{format(shown)}</span>;
}

/** Fade-up stagger of the page content when it first appears (view changes animate in). */
export function useEnter(ready: boolean, key: string) {
  const done = useRef<string | null>(null);
  useLayoutEffect(() => {
    if (!ready || done.current === key || reduceMotion()) return;
    done.current = key;
    const ctx = gsap.context(() => {
      gsap.from('#content > *:not(.home-hero):not(.tickets)', { opacity: 0, y: 16, duration: 0.55, stagger: 0.05, ease: 'power3.out', clearProps: 'opacity,transform' });
    });
    return () => ctx.revert();
  }, [ready, key]);
}

export const Centered = ({ pill, children }: { pill: string; children: ReactNode }) => (
  <div className="centered-h">
    <span className="pill">
      <i />
      {pill}
    </span>
    <h2 className="h2">{children}</h2>
  </div>
);
