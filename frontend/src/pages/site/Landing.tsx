// The website (/), ported from the prototype: hero, pinned stats, loop accordion, assistant, night CTA, footer.
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import { useSession } from '../../api/session';
import { useHtmlMode } from '../../App';
import { LineChart } from '../../components/Charts';
import { Words } from '../../components/Home';
import { BrandSvg } from '../../components/Icons';
import { useToast } from '../../components/ui';
import {
  WaterCanvas,
  drawFish,
  fitCanvas,
  makeFish,
  rand,
  reduceMotion,
  useCanvasLoop,
  type Fish,
} from '../../components/Water';
import { fmt, hhmm } from '../../lib/format';

gsap.registerPlugin(ScrollTrigger);
let introDone = false;

type Showcase = {
  available: boolean;
  do?: number;
  temp?: number;
  ph?: number;
  series?: { times: string[]; values: number[] };
  low?: { value: number; time: string; index: number };
  warn?: number;
};

const statsState = { level: 0.62 };

function StatsWater() {
  const ref = useRef<HTMLCanvasElement>(null);
  useCanvasLoop(ref, (c) => {
    let bub: { x: number; y: number; r: number; vy: number; ph: number }[] = [];
    let fish: Fish[] | null = null;
    let lw = 0;
    const reduce = reduceMotion();
    return (t: number) => {
      const { ctx, w, h } = fitCanvas(c);
      ctx.clearRect(0, 0, w, h);
      const surf = h * (1 - (0.06 + 0.66 * statsState.level));
      if (!fish || Math.abs(w - lw) > 80) {
        fish = makeFish(w < 700 ? 5 : 9, w, h, 0);
        lw = w;
      }
      const wave = (x: number, k: number) =>
        surf + Math.sin(x * 0.011 + t * 0.0012 * k) * 7 + Math.sin(x * 0.027 - t * 0.0009) * 3;
      ctx.fillStyle = 'rgba(143,206,192,.35)';
      ctx.beginPath();
      ctx.moveTo(0, h);
      for (let x = 0; x <= w; x += 12) ctx.lineTo(x, wave(x + 60, 0.7) - 8);
      ctx.lineTo(w, h);
      ctx.fill();
      const g = ctx.createLinearGradient(0, surf, 0, h);
      g.addColorStop(0, 'rgba(170,220,208,.9)');
      g.addColorStop(0.45, 'rgba(45,138,128,.9)');
      g.addColorStop(1, 'rgba(12,48,56,.95)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(0, h);
      for (let x = 0; x <= w; x += 10) ctx.lineTo(x, wave(x, 1));
      ctx.lineTo(w, h);
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,.7)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      for (let x = 0; x <= w; x += 10) {
        const y = wave(x, 1);
        if (x) ctx.lineTo(x, y);
        else ctx.moveTo(x, y);
      }
      ctx.stroke();
      fish.forEach((f) => {
        const fy = surf + 40 + (h - surf - 60) * (0.2 + 0.7 * (((f.off % 1) + 1) % 1));
        if (fy > h - 10 || h - surf < 90) return;
        f.x += f.dir * f.sp;
        f.ph += 0.15;
        if (f.dir > 0 && f.x > w + 40) f.x = -40;
        if (f.dir < 0 && f.x < -40) f.x = w + 40;
        drawFish(
          ctx,
          f.x,
          fy + Math.sin(t * 0.001 + f.off) * 4,
          8 + f.z * 12,
          f.dir,
          f.ph,
          'rgba(6,34,40,' + (0.25 + f.z * 0.35).toFixed(2) + ')',
        );
      });
      if (!reduce && Math.random() < 0.4)
        bub.push({ x: Math.random() * w, y: h + 4, r: rand(1.2, 4), vy: rand(0.4, 1.1), ph: Math.random() * 6 });
      bub = bub.filter((b) => b.y > surf + 4);
      ctx.strokeStyle = 'rgba(235,255,250,.7)';
      ctx.lineWidth = 1;
      bub.forEach((b) => {
        b.y -= b.vy;
        b.ph += 0.07;
        ctx.beginPath();
        ctx.arc(b.x + Math.sin(b.ph) * 2, b.y, b.r, 0, 7);
        ctx.stroke();
      });
    };
  });
  return <canvas id="statsWater" ref={ref} aria-hidden="true" />;
}

function NightLake() {
  const ref = useRef<HTMLCanvasElement>(null);
  useCanvasLoop(ref, (c) => {
    let stars: { x: number; y: number; r: number; p: number }[] | null = null;
    let lw = 0;
    return (t: number) => {
      const { ctx, w, h } = fitCanvas(c);
      const hz = h * 0.42;
      if (!stars || Math.abs(w - lw) > 80) {
        stars = Array.from({ length: 110 }, () => ({
          x: Math.random() * w,
          y: Math.random() * hz * 0.9,
          r: rand(0.4, 1.3),
          p: Math.random() * 6,
        }));
        lw = w;
      }
      let g = ctx.createLinearGradient(0, 0, 0, hz);
      g.addColorStop(0, '#0a1430');
      g.addColorStop(0.7, '#16305a');
      g.addColorStop(1, '#2c4f7a');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, hz + 1);
      stars.forEach((s) => {
        ctx.fillStyle = 'rgba(230,240,255,' + (0.35 + 0.35 * Math.sin(t * 0.001 + s.p)).toFixed(2) + ')';
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, 7);
        ctx.fill();
      });
      const mx = w * 0.76;
      const my = hz * 0.38;
      const mg = ctx.createRadialGradient(mx, my, 0, mx, my, 120);
      mg.addColorStop(0, 'rgba(255,248,225,.55)');
      mg.addColorStop(1, 'rgba(255,248,225,0)');
      ctx.fillStyle = mg;
      ctx.fillRect(mx - 130, my - 130, 260, 260);
      ctx.fillStyle = '#fff6df';
      ctx.beginPath();
      ctx.arc(mx, my, 22, 0, 7);
      ctx.fill();
      ctx.fillStyle = '#0c1b38';
      ctx.beginPath();
      ctx.moveTo(0, hz);
      for (let x = 0; x <= w; x += 16)
        ctx.lineTo(
          x,
          hz -
            18 -
            Math.sin(x * 0.004) * 22 -
            Math.sin(x * 0.011 + 1) * 10 -
            (x < w * 0.3 ? 30 * Math.sin((x / w) * Math.PI * 3.2) : 0),
        );
      ctx.lineTo(w, hz);
      ctx.fill();
      g = ctx.createLinearGradient(0, hz, 0, h);
      g.addColorStop(0, '#1c3a64');
      g.addColorStop(1, '#050d1f');
      ctx.fillStyle = g;
      ctx.fillRect(0, hz, w, h - hz);
      for (let i = 0; i < 34; i++) {
        const y = hz + 6 + i * i * 0.5;
        if (y > h) break;
        const len = (30 - i * 0.5) * (0.6 + 0.4 * Math.sin(t * 0.002 + i));
        ctx.fillStyle = 'rgba(255,240,205,' + (0.5 - i * 0.012).toFixed(3) + ')';
        ctx.fillRect(mx - len / 2 + Math.sin(t * 0.0015 + i * 0.7) * 6, y, Math.max(2, len), 1.4);
      }
      const pens: [number, number, number][] = [
        [w * 0.18, hz + (h - hz) * 0.36, w * 0.13],
        [w * 0.42, hz + (h - hz) * 0.5, w * 0.17],
        [w * 0.72, hz + (h - hz) * 0.62, w * 0.2],
      ];
      pens.forEach(([x, y, rx], i) => {
        const ry = rx * 0.22;
        ctx.strokeStyle = 'rgba(150,180,215,.35)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.ellipse(x, y, rx, ry, 0, 0, 7);
        ctx.stroke();
        ctx.strokeStyle = 'rgba(150,180,215,.18)';
        ctx.beginPath();
        ctx.ellipse(x, y + 4, rx * 0.96, ry * 0.92, 0, 0, 7);
        ctx.stroke();
        ctx.fillStyle = 'rgba(20,40,80,.35)';
        ctx.beginPath();
        ctx.ellipse(x, y + 3, rx * 0.93, ry * 0.86, 0, 0, 7);
        ctx.fill();
        for (let k = 0; k < 4; k++) {
          const ang = (k * Math.PI) / 2 + 0.4;
          const bx = x + Math.cos(ang) * rx;
          const by = y + Math.sin(ang) * ry;
          const on = (t / 1000 + i * 0.6 + k * 0.35) % 2.4 < 0.18;
          ctx.fillStyle = '#1a2a4a';
          ctx.fillRect(bx - 2, by - 6, 4, 6);
          const col = i === 2 && k === 1 ? '255,190,90' : '120,255,190';
          ctx.fillStyle = 'rgba(' + col + ',' + (on ? 1 : 0.35) + ')';
          ctx.beginPath();
          ctx.arc(bx, by - 8, on ? 3 : 2, 0, 7);
          ctx.fill();
          if (on) {
            const bg = ctx.createRadialGradient(bx, by - 8, 0, bx, by - 8, 22);
            bg.addColorStop(0, 'rgba(' + col + ',.4)');
            bg.addColorStop(1, 'rgba(' + col + ',0)');
            ctx.fillStyle = bg;
            ctx.fillRect(bx - 22, by - 30, 44, 44);
          }
        }
      });
      ctx.strokeStyle = 'rgba(160,190,230,.08)';
      ctx.lineWidth = 1;
      for (let i = 0; i < 14; i++) {
        const y = hz + 20 + i * ((h - hz) / 14);
        ctx.beginPath();
        for (let x = 0; x <= w; x += 20) {
          const yy = y + Math.sin(x * 0.02 + t * 0.0008 + i) * 1.5;
          if (x) ctx.lineTo(x, yy);
          else ctx.moveTo(x, yy);
        }
        ctx.stroke();
      }
    };
  });
  return (
    <canvas
      id="nightCanvas"
      ref={ref}
      role="img"
      aria-label="Floating fish pens on a lake before dawn, sensor buoys blinking"
    />
  );
}

function SqField({ count }: { count: number }) {
  const squares = useMemo(
    () =>
      Array.from({ length: count }, () => ({
        left: Math.floor(Math.random() * 30) * 48 - 10,
        top: Math.floor(Math.random() * 6) * 48 + 6,
      })),
    [count],
  );
  return (
    <div
      className="sq-field"
      style={{
        position: 'absolute',
        inset: '0 0 auto 0',
        height: '42%',
        zIndex: 1,
        pointerEvents: 'none',
        WebkitMaskImage: 'linear-gradient(#000,transparent)',
        maskImage: 'linear-gradient(#000,transparent)',
      }}
    >
      {squares.map((q, i) => (
        <div
          key={i}
          className="grid-sq"
          style={{ left: q.left, top: q.top, width: 46, height: 46, opacity: reduceMotion() ? 0.6 : 0 }}
        />
      ))}
    </div>
  );
}

const GLASS: [number, number][] = [
  [3, 62],
  [3, 69],
  [6.5, 69],
  [10, 69],
  [3, 76],
  [-1, 68],
  [45.5, 74],
  [49, 78],
  [49, 74],
  [52.5, 74],
  [86, 56],
  [86, 65],
  [82, 74],
  [89.5, 74],
  [86, 82],
];
const CARDS = [
  { small: 'Night oxygen dips flagged before dawn', to: 94, dec: 0, suf: '%' },
  { small: 'Median time from alert to action', to: 4.2, dec: 1, suf: ' min' },
  { small: 'Feed saved by skipping risky evening meals', to: 12, dec: 0, suf: '%' },
  { small: 'Sensor uptime across 12 probes', to: 99.6, dec: 1, suf: '%' },
];

export default function Landing() {
  useHtmlMode('site');
  const nav = useNavigate();
  const toast = useToast();
  const { login, status, me } = useSession();
  const [show, setShow] = useState<Showcase | null>(null);
  const siteRef = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);
  const isMobile = typeof window !== 'undefined' && innerWidth <= 760;

  useEffect(() => {
    const load = () =>
      api<Showcase>('/api/public/showcase')
        .then(setShow)
        .catch(() => undefined);
    load();
    const t = window.setInterval(load, 6000);
    return () => window.clearInterval(t);
  }, []);

  const tryDemo = async (ask?: string) => {
    try {
      if (!(status === 'in' && me?.role === 'owner' && me.user.email === 'nadia@lacvert.farm'))
        await login('owner', 'nadia@lacvert.farm', 'demo1234');
      nav('/owner', { state: ask ? { ask } : undefined });
    } catch {
      toast(
        <>
          <b>The demo is not available</b> · start the back end and load the demo farm
        </>,
      );
    }
  };

  const scrollTo = (id: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    const el = document.querySelector(id) as HTMLElement | null;
    if (!el) return;
    const l = (window as any).__lenis as Lenis | undefined;
    if (l) l.scrollTo(el, { duration: 1.6 });
    else el.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth' });
  };

  // motion: intro, Lenis smooth scroll, scroll-triggered reveals (timings copied from the prototype)
  useLayoutEffect(() => {
    const reduce = reduceMotion();
    const site = siteRef.current!;
    const q = (s: string) => Array.from(site.querySelectorAll(s));
    const setCounters = (p: number) =>
      q('.stats .card b').forEach((b, i) => {
        const c = CARDS[i];
        const v = c.to * p;
        b.innerHTML =
          (c.dec ? v.toFixed(c.dec) : Math.round(v).toLocaleString('en-US')) +
          (c.suf.trim() === 'min' ? '<sup>min</sup>' : c.suf);
      });
    let lenis: Lenis | null = null;
    const tick = (t: number) => lenis?.raf(t * 1000);
    const ctx = gsap.context(() => {
      if (!reduce) {
        lenis = new Lenis({
          duration: 1.25,
          easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
          smoothWheel: true,
        });
        (window as any).__lenis = lenis;
        lenis.on('scroll', ScrollTrigger.update);
        gsap.ticker.add(tick);
        gsap.ticker.lagSmoothing(0);
      }
      const finish = () => {
        introDone = true;
        document.body.classList.remove('intro');
        if (backdropRef.current) backdropRef.current.style.display = 'none';
        setCounters(1);
        statsState.level = 0.62;
      };
      const setupScroll = () => {
        gsap
          .timeline({ scrollTrigger: { trigger: '#hero', start: 'top top', end: 'bottom top', scrub: true } })
          .to('#heroCopy', { yPercent: -50 }, 0)
          .to('.hero-media', { yPercent: 8 }, 0);
        q('.hero [data-par]').forEach((el) =>
          gsap.to(el, {
            y: +(el as HTMLElement).dataset.par! * 2,
            ease: 'none',
            scrollTrigger: { trigger: '#hero', start: 'top top', end: 'bottom top', scrub: true },
          }),
        );
        q('.reveal').forEach((el) =>
          gsap.from(el, {
            opacity: 0,
            y: 16,
            duration: 0.8,
            ease: 'power3.out',
            scrollTrigger: { trigger: el, start: 'top 88%' },
          }),
        );
        q('.stats .split, .loop .split, .assist .split, .cta .split').forEach((el) =>
          gsap.from(el.querySelectorAll('.w'), {
            opacity: 0,
            y: 22,
            filter: 'blur(8px)',
            duration: 0.9,
            stagger: 0.06,
            ease: 'power3.out',
            scrollTrigger: { trigger: el, start: 'top 82%' },
          }),
        );
        const mm = gsap.matchMedia();
        mm.add('(min-width:901px)', () => {
          gsap.from('.stats .card', {
            y: 40,
            opacity: 0,
            stagger: 0.08,
            duration: 0.9,
            ease: 'power3.out',
            scrollTrigger: { trigger: '.cards', start: 'top 75%' },
          });
          const proxy = { p: 0 };
          setCounters(0);
          statsState.level = 0;
          gsap
            .timeline({ scrollTrigger: { trigger: '#stats', start: 'top top', end: '+=120%', pin: true, scrub: 1 } })
            .to(proxy, {
              p: 1,
              ease: 'none',
              onUpdate() {
                setCounters(proxy.p);
                statsState.level = proxy.p;
              },
            });
          return () => {
            setCounters(1);
            statsState.level = 0.62;
          };
        });
        mm.add('(max-width:900px)', () => {
          gsap.from('.stats .card', {
            y: 30,
            opacity: 0,
            stagger: 0.08,
            duration: 0.8,
            scrollTrigger: { trigger: '.cards', start: 'top 85%' },
          });
          const proxy = { p: 0 };
          setCounters(0);
          gsap.to(proxy, {
            p: 1,
            duration: 2,
            ease: 'power2.out',
            onUpdate: () => setCounters(proxy.p),
            scrollTrigger: { trigger: '.cards', start: 'top 80%' },
          });
          gsap.fromTo(
            statsState,
            { level: 0 },
            {
              level: 0.62,
              ease: 'none',
              scrollTrigger: { trigger: '#stats', start: 'top bottom', end: 'bottom bottom', scrub: true },
            },
          );
        });
        mm.add('(min-width:761px)', () => {
          gsap.from('.panel-in', {
            y: 120,
            opacity: 0,
            duration: 1.1,
            stagger: 0.12,
            ease: 'power3.out',
            scrollTrigger: { trigger: '#loop', start: 'top 60%' },
          });
        });
        mm.add('(max-width:760px)', () => {
          q('.panel').forEach((p) =>
            gsap.from(p.children, {
              y: 40,
              opacity: 0,
              duration: 0.9,
              stagger: 0.1,
              scrollTrigger: { trigger: p, start: 'top 85%' },
            }),
          );
        });
        gsap.fromTo(
          '#nightCanvas',
          { yPercent: -12 },
          {
            yPercent: 0,
            ease: 'none',
            scrollTrigger: { trigger: '#cta', start: 'top bottom', end: 'bottom bottom', scrub: true },
          },
        );
        gsap.from('#ctaCard', {
          y: 80,
          scale: 0.94,
          opacity: 0,
          filter: 'blur(10px)',
          duration: 1.2,
          ease: 'power3.out',
          scrollTrigger: { trigger: '#cta', start: 'top 60%' },
        });
        // footer logo: three bubbles bounce, merge into the fish, ring draws
        gsap.set('#fRing', { attr: { 'stroke-dashoffset': 233 } });
        gsap.set('#fMark', { attr: { 'stroke-dashoffset': 120 } });
        const dots = q('.fdot');
        dots.forEach((d, i) => gsap.set(d, { opacity: 1, attr: { cx: 24 + 16 * i, cy: 40, r: 4.5 } }));
        gsap
          .timeline({ scrollTrigger: { trigger: '#footer', start: 'top 92%' } })
          .to(dots, { y: -8, duration: 0.25, stagger: 0.08, yoyo: true, repeat: 3, ease: 'sine.inOut' })
          .to(dots, { attr: { cx: 27, cy: 38 }, duration: 0.45, ease: 'power3.inOut' })
          .to([dots[1], dots[2]], { opacity: 0, duration: 0.1 })
          .to('#fMark', { attr: { 'stroke-dashoffset': 0 }, duration: 0.7, ease: 'power3.out' }, '-=.05')
          .to(dots[0], { attr: { r: 3.2 }, duration: 0.3, ease: 'back.out(3)' }, '<')
          .to('#fRing', { attr: { 'stroke-dashoffset': 0 }, duration: 0.9, ease: 'power2.inOut' }, '-=.3');
        q('.grid-sq').forEach((g) =>
          gsap.to(g, { opacity: 1, duration: 1.2, yoyo: true, repeat: -1, delay: rand(0, 4), repeatDelay: rand(0, 3) }),
        );
        q('#heroGlass .glass').forEach((g) =>
          gsap.to(g, {
            opacity: 0.15,
            duration: 0.9,
            yoyo: true,
            repeat: -1,
            ease: 'sine.inOut',
            delay: rand(0, 3),
            repeatDelay: rand(1, 4),
          }),
        );
        ScrollTrigger.refresh();
      };

      if (reduce || introDone) {
        finish();
        if (!reduce) setupScroll();
        return;
      }
      document.body.classList.add('intro');
      lenis?.stop();
      const words = q('#heroTitle .w');
      gsap.set(words, { opacity: 0, y: 24, filter: 'blur(10px)' });
      gsap.set('.nav', { opacity: 0, y: -16 });
      gsap.set('.reveal-hero', { opacity: 0, y: 14 });
      gsap
        .timeline({
          delay: 0.25,
          onComplete() {
            document.body.classList.remove('intro');
            gsap.set('#site', { clearProps: 'all' });
            if (backdropRef.current) backdropRef.current.style.display = 'none';
            introDone = true;
            lenis?.start();
            setupScroll();
          },
        })
        .fromTo(
          '#site',
          { scale: 0.9, borderRadius: 28 },
          { scale: 1, borderRadius: 0, duration: 1.4, ease: 'expo.inOut' },
        )
        .to('.nav', { opacity: 1, y: 0, duration: 0.8, ease: 'power3.out' }, '-=.5')
        .to(words, { opacity: 1, y: 0, filter: 'blur(0px)', duration: 1, stagger: 0.07, ease: 'power3.out' }, '-=.7')
        .to('.reveal-hero', { opacity: 1, y: 0, duration: 0.8, stagger: 0.1, ease: 'power3.out' }, '-=.6')
        .from('.mist-l', { x: -120, opacity: 0, duration: 1.6, ease: 'power3.out' }, 0.4)
        .from('.mist-r', { x: 120, opacity: 0, duration: 1.6, ease: 'power3.out' }, 0.4)
        .from(
          '#heroGlass .glass, .reading',
          { opacity: 0, scale: 0.6, duration: 0.6, stagger: { each: 0.05, from: 'random' }, ease: 'back.out(2)' },
          '-=1',
        );
    }, site);
    return () => {
      ctx.revert();
      gsap.ticker.remove(tick);
      lenis?.destroy();
      (window as any).__lenis = undefined;
      document.body.classList.remove('intro');
    };
  }, []);

  // loop accordion (hover / focus / click on desktop)
  const [active, setActive] = useState(0);

  const low = show?.low;
  const chart =
    show?.series && show.series.values.length > 1 ? (
      <LineChart
        values={show.series.values}
        times={show.series.times}
        min={3}
        max={10}
        dec={2}
        warn={show.warn ?? 7}
        dir="below"
        color="#1d6f6a"
        h={200}
        label="Dissolved oxygen in Basin 3, last 24 hours"
        mark={
          low && low.value < (show.warn ?? 7)
            ? { i: low.index, label: hhmm(low.time) + ' · ' + fmt(low.value, 2) }
            : null
        }
      />
    ) : null;

  return (
    <>
      {!introDone && <div className="backdrop" aria-hidden="true" ref={backdropRef} />}
      <div id="site" ref={siteRef}>
        <section className="hero" id="hero">
          <nav className="nav" aria-label="Main">
            <a className="brand" href="#hero" aria-label="FishFarm home" onClick={scrollTo('#hero')}>
              <BrandSvg />
              fishfarm
            </a>
            <div className="nav-links">
              <a href="#loop" onClick={scrollTo('#loop')}>
                How it works
              </a>
              <a href="#assistant" onClick={scrollTo('#assistant')}>
                Assistant
              </a>
              <Link to="/owner-auth">Sign in</Link>
            </div>
            <button className="btn" type="button" onClick={() => tryDemo()}>
              Try the live demo
            </button>
          </nav>
          <div className="mist mist-l drift-a" data-par="-60" aria-hidden="true" />
          <div className="mist mist-r drift-b" data-par="-90" aria-hidden="true" />
          <div className="hero-copy" id="heroCopy">
            <h1 id="heroTitle" className="split">
              <Words text="Know your water" />
              <br />
              <Words text="before your " />
              <em>
                <Words text="fish do." />
              </em>
            </h1>
            <p className="hero-sub reveal-hero">
              FishFarm reads temperature, pH and dissolved oxygen in every basin every six seconds, warns the right
              person, and explains what to do.
            </p>
            <div className="hero-ctas reveal-hero">
              <Link className="btn" to="/owner-auth" state={{ sub: 'register' }}>
                Create your farm
              </Link>
              <button className="btn ghost" type="button" onClick={() => tryDemo()}>
                Try the live demo
              </button>
            </div>
          </div>
          <div className="hero-media">
            <WaterCanvas
              id="heroCanvas"
              opts={{ palette: 'light', fish: 28 }}
              label="Fish swimming in a basin with aerator bubbles"
            />
          </div>
          <div className="hero-glass" id="heroGlass" aria-hidden="true">
            {GLASS.map(([x, y], i) => {
              const center = x > 40 && x < 60;
              const sz = center ? 'clamp(26px,3.2vw,42px)' : 'clamp(34px,5vw,70px)';
              return (
                <div
                  key={i}
                  className="glass"
                  style={{
                    left: `${x}%`,
                    top: `${y}%`,
                    width: sz,
                    aspectRatio: '1',
                    display: isMobile && i % 2 ? 'none' : undefined,
                  }}
                />
              );
            })}
          </div>
          <div className="reading r1" style={{ left: '7%', top: '70%' }}>
            <span className="lbl">
              <i />
              Basin 3 · dissolved oxygen
            </span>
            <b data-hero="do">{fmt(show?.do ?? 7.42, 2)}</b>
            <span className="u">mg/L</span>
          </div>
          <div className="reading r2" style={{ left: '44%', top: '84%' }}>
            <span className="lbl">
              <i />
              Basin 1 · water
            </span>
            <b data-hero="temp">{fmt(show?.temp ?? 28.1, 1)}</b>
            <span className="u">°C</span>
          </div>
          <div className="reading r3" style={{ right: '7%', top: '66%' }}>
            <span className="lbl">
              <i />
              Basin 2 · acidity
            </span>
            <b data-hero="ph">{fmt(show?.ph ?? 7.31, 2)}</b>
            <span className="u">pH</span>
          </div>
        </section>

        <section className="stats" id="stats">
          <StatsWater />
          <SqField count={20} />
          <div className="stats-inner">
            <span className="pill reveal">
              <i />
              Demo farm, last 30 days
            </span>
            <h2 className="h2 split">
              <Words text="Every basin checked" />
              <br />
              <Words text="14,400 times a day." />
            </h2>
            <div className="cards">
              {CARDS.map((c) => (
                <div className="card" key={c.small}>
                  <small>{c.small}</small>
                  <b>
                    {c.dec ? c.to.toFixed(c.dec) : c.to}
                    {c.suf.trim() === 'min' ? <sup>min</sup> : c.suf}
                  </b>
                </div>
              ))}
            </div>
            <div className="cards-shadow" />
            <div className="built">
              <span className="l">Built with</span>
              <span>PostgreSQL</span>
              <span>FastAPI</span>
              <span>pandas</span>
              <span>scikit-learn</span>
              <span>React</span>
              <span>Docker</span>
            </div>
            <p className="foot-note">Figures come from the simulated demo farm.</p>
          </div>
        </section>

        <section className="loop" id="loop">
          <div className="loop-head">
            <span className="pill reveal">From sensor to action</span>
            <h2 className="h2 split">
              <Words text="One reading, three hands," />
              <br />
              <Words text="six seconds." />
            </h2>
          </div>
          <div className="track" id="track">
            {[
              {
                tag: 'every 6 s · 3 probes per basin',
                h: 'The sensor reads',
                p: 'Probes in each basin measure temperature, pH and dissolved oxygen and send every reading to the data pipeline.',
                bubbles: [
                  [10, 60, 22, 0],
                  [44, 24, 14, -2],
                  [30, 0, 9, -4],
                ],
              },
              {
                tag: 'clean · compare · store',
                h: 'The pipeline checks',
                p: 'Each reading is cleaned, compared with the safe range for the species in that basin, and stored for the charts and the oxygen prediction model.',
                bubbles: [
                  [16, 50, 18, 0],
                  [50, 20, 11, -3],
                ],
              },
              {
                tag: 'worker · technician · owner',
                h: 'The right person acts',
                p: 'Water problems go to the worker on shift. A sensor that stops changing goes to the technician. The owner sees the summary and the money.',
                bubbles: [
                  [6, 56, 20, 0],
                  [40, 28, 13, -1.5],
                  [62, 4, 8, -3.5],
                ],
              },
            ].map((s, i) => (
              <div
                key={i}
                className={`panel${active === i ? ' is-active' : ''}`}
                tabIndex={0}
                aria-label={`Step ${i + 1}: ${s.h}`}
                onMouseEnter={() => !isMobile && setActive(i)}
                onFocus={() => setActive(i)}
                onClick={() => setActive(i)}
              >
                <div className="panel-in">
                  <span className="num">{i + 1}</span>
                  <div className="step">
                    <div className="bubbles" aria-hidden="true">
                      {s.bubbles.map(([l, t, w, d], k) => (
                        <i
                          key={k}
                          style={{ left: l, top: t, width: w, height: w, animationDelay: d ? `${d}s` : undefined }}
                        />
                      ))}
                    </div>
                    <span className="tag">{s.tag}</span>
                    <h3>{s.h}</h3>
                    <p>{s.p}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="assist" id="assistant">
          <div className="assist-grid">
            <div className="assist-copy">
              <span className="pill reveal">Farm assistant</span>
              <h2 className="h2 split">
                <Words text="Ask your farm" />
                <br />
                <Words text="why." />
              </h2>
              <p className="reveal">
                The assistant reads the same live data as your dashboard, checks the safe range for each species, and
                answers with numbers, sources and next steps. Alerts still come from the alert engine, never from the
                chat.
              </p>
              <ul className="ticks reveal">
                <li>Explains any alert, chart or cost in plain words</li>
                <li>Runs what-if scenarios on feeding and stocking</li>
                <li>Asks for your approval before it creates a task</li>
              </ul>
              <button
                className="btn reveal"
                type="button"
                onClick={() => tryDemo('Why did oxygen drop in Basin 3 last night?')}
              >
                Ask it in the demo
              </button>
            </div>
            <div className="chat-demo reveal" aria-label="Example conversation with the farm assistant">
              <div className="chat-top">
                <b>Farm assistant</b>
                <span className="mono">reads live data</span>
              </div>
              <div className="msg-user">Why did oxygen drop in Basin 3 last night?</div>
              <div className="msg-ai">
                <div className="steps">
                  <span className="stepchip">
                    <span className="ok">✓</span>Read Basin 3 oxygen, last 24 h
                  </span>
                  <span className="stepchip">
                    <span className="ok">✓</span>Checked rainbow trout limits
                  </span>
                </div>
                <p>
                  Oxygen fell to{' '}
                  <b id="demoMin">{low ? `${fmt(low.value, 1)} mg/L at ${hhmm(low.time)}` : '5.4 mg/L at 04:15'}</b>,
                  under the 7.0 mg/L warning level for rainbow trout. Algae stop making oxygen after sunset but keep
                  using it until dawn, and the evening feed added demand.
                </p>
                <div className="chart" id="showcaseChart">
                  {chart}
                </div>
                <div className="srcs">
                  <span className="src">FAO · Water quality in aquaculture</span>
                  <span className="src">OMAFRA · Rainbow trout profile</span>
                </div>
                <div className="approve">
                  <span className="mini">
                    Suggested task: <b>Run the Basin 3 aerator 22:00–07:00 tonight</b>
                  </span>
                  <div className="row" style={{ justifyContent: 'flex-start' }}>
                    <button
                      className="small-btn primary"
                      type="button"
                      onClick={() => tryDemo('Why did oxygen drop in Basin 3 last night?')}
                    >
                      Approve in the demo
                    </button>
                    <button className="small-btn" type="button" onClick={() => tryDemo()}>
                      Open the demo
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="cta" id="cta">
          <SqField count={14} />
          <div className="cta-img">
            <NightLake />
          </div>
          <div className="cta-card" id="ctaCard">
            <span className="pill">Night shift</span>
            <h2 className="h2 split">
              <Words text="Sleep through the" />
              <br />
              <Words text="4 a.m. oxygen dip." />
            </h2>
            <p className="reveal">
              FishFarm watches every basin through the night and wakes the right person only when the water needs it.
            </p>
            <div className="hero-ctas reveal">
              <Link className="btn" to="/owner-auth" state={{ sub: 'register' }}>
                Create your farm
              </Link>
              <Link className="btn ghost" to="/worker-auth">
                Team sign in
              </Link>
            </div>
          </div>
        </section>

        <footer id="footer">
          <svg className="f-logo" viewBox="0 0 80 80" style={{ overflow: 'visible' }} aria-label="FishFarm">
            <circle
              id="fRing"
              cx="40"
              cy="40"
              r="37"
              fill="none"
              stroke="#0c1d22"
              strokeWidth="2.4"
              strokeDasharray="233"
              strokeDashoffset="0"
              transform="rotate(-90 40 40)"
            />
            <circle className="fdot" cx="27" cy="38" r="3.2" fill="#0c1d22" />
            <circle className="fdot" cx="27" cy="38" r="3.2" fill="#0c1d22" opacity="0" />
            <circle className="fdot" cx="27" cy="38" r="3.2" fill="#0c1d22" opacity="0" />
            <path
              id="fMark"
              d="M18 40C26 29 42 29 51 40 42 51 26 51 18 40ZM51 40 61 32M51 40 61 48"
              fill="none"
              stroke="#0c1d22"
              strokeWidth="5"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray="120"
              strokeDashoffset="0"
            />
          </svg>
          <nav className="f-links" aria-label="Footer">
            <a href="#loop" onClick={scrollTo('#loop')}>
              How it works
            </a>
            <a href="#assistant" onClick={scrollTo('#assistant')}>
              Assistant
            </a>
            <Link to="/owner-auth">Owner sign in</Link>
            <Link to="/worker-auth">Team sign in</Link>
            <a
              href="#demo"
              onClick={(e) => {
                e.preventDefault();
                tryDemo();
              }}
            >
              Live demo
            </a>
          </nav>
          <div className="f-social">
            <span>pH · °C · O₂</span>
          </div>
          <p className="f-copy">© 2026 FishFarm · Portfolio project · All figures come from a simulated farm.</p>
        </footer>
      </div>
    </>
  );
}
