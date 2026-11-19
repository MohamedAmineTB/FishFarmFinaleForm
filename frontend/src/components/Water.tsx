// Canvas scenes ported from the prototype (makeWater, drawFish, stats water, night lake).
import { useEffect, useRef, type RefObject } from 'react';

export const reduceMotion = () =>
  typeof window !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
const rand = (a: number, b: number) => a + Math.random() * (b - a);
const DPR = () => Math.min(window.devicePixelRatio || 1, 1.5);

export function fitCanvas(c: HTMLCanvasElement) {
  const r = c.getBoundingClientRect();
  const w = Math.max(1, Math.round(r.width));
  const h = Math.max(1, Math.round(r.height));
  const d = DPR();
  if (c.width !== Math.round(w * d) || c.height !== Math.round(h * d)) {
    c.width = Math.round(w * d);
    c.height = Math.round(h * d);
  }
  const ctx = c.getContext('2d')!;
  ctx.setTransform(d, 0, 0, d, 0, 0);
  return { ctx, w, h };
}

export function drawFish(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  s: number,
  dir: number,
  ph: number,
  col: string,
) {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(dir, 1);
  ctx.fillStyle = col;
  const wag = Math.sin(ph) * s * 0.22;
  ctx.beginPath();
  ctx.moveTo(s, 0);
  ctx.quadraticCurveTo(s * 0.1, -s * 0.52, -s * 0.75, wag * 0.3);
  ctx.quadraticCurveTo(s * 0.1, s * 0.52, s, 0);
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(-s * 0.65, wag * 0.3);
  ctx.lineTo(-s * 1.3, -s * 0.42 + wag);
  ctx.lineTo(-s * 1.18, wag * 0.9);
  ctx.lineTo(-s * 1.3, s * 0.42 + wag);
  ctx.closePath();
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(s * 0.15, -s * 0.36);
  ctx.lineTo(-s * 0.2, -s * 0.62);
  ctx.lineTo(-s * 0.3, -s * 0.3);
  ctx.fill();
  ctx.restore();
}

export type Fish = { x: number; y: number; z: number; dir: number; sp: number; ph: number; off: number };
export function makeFish(n: number, w: number, h: number, top: number): Fish[] {
  return Array.from({ length: n }, () => {
    const z = Math.random();
    return {
      x: Math.random() * w,
      y: top + (h - top) * (0.15 + 0.75 * Math.random()),
      z,
      dir: Math.random() < 0.78 ? 1 : -1,
      sp: 0.25 + z * 0.55,
      ph: Math.random() * 6,
      off: Math.random() * 6,
    };
  });
}

const PALETTES = {
  light: {
    stops: [
      [0, '#cfe9e2'],
      [0.35, '#6fb3a8'],
      [0.75, '#1e6a6a'],
      [1, '#0c3038'],
    ] as [number, string][],
    fish: '8,38,44',
    ray: 0.16,
    bubble: '235,255,250',
  },
  dark: {
    stops: [
      [0, '#1b5a5e'],
      [0.5, '#0f3a42'],
      [1, '#071f25'],
    ] as [number, string][],
    fish: '160,220,205',
    ray: 0.07,
    bubble: '190,240,225',
  },
};

export type WaterOpts = {
  palette?: 'light' | 'dark';
  fish?: number;
  top?: number;
  scale?: number;
  aerators?: number[];
};

/** One reusable underwater scene: light rays, plankton, fish and aerator bubbles. */
export function makeWater(c: HTMLCanvasElement, o: WaterOpts) {
  const pal = PALETTES[o.palette || 'light'];
  const reduce = reduceMotion();
  let fish: Fish[] | null = null;
  let bubbles: { x: number; y: number; r: number; vy: number; ph: number }[] = [];
  let plankton: { x: number; y: number; r: number; s: number }[] = [];
  let lastW = 0;
  return function draw(t: number) {
    const { ctx, w, h } = fitCanvas(c);
    if (!fish || Math.abs(w - lastW) > 80) {
      fish = makeFish(Math.round((o.fish || 28) * (w < 700 ? 0.5 : 1)), w, h, h * (o.top ?? 0.18));
      plankton = Array.from({ length: Math.round(w / 18) }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        r: rand(0.6, 1.8),
        s: rand(0.05, 0.2),
      }));
      lastW = w;
    }
    const g = ctx.createLinearGradient(0, 0, 0, h);
    pal.stops.forEach((s) => g.addColorStop(s[0], s[1]));
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    for (let i = 0; i < 6; i++) {
      const x0 = w * (0.06 + 0.18 * i) + Math.sin(t * 0.00025 + i * 1.7) * 40;
      const rg = ctx.createLinearGradient(0, 0, 0, h * 0.9);
      rg.addColorStop(0, 'rgba(255,255,255,' + pal.ray + ')');
      rg.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = rg;
      ctx.beginPath();
      ctx.moveTo(x0 - 18, 0);
      ctx.lineTo(x0 + 46, 0);
      ctx.lineTo(x0 + 180, h * 0.9);
      ctx.lineTo(x0 + 40, h * 0.9);
      ctx.closePath();
      ctx.fill();
    }
    ctx.fillStyle = 'rgba(235,250,245,.3)';
    plankton.forEach((p) => {
      p.y -= p.s;
      p.x += Math.sin(t * 0.0004 + p.y * 0.02) * 0.15;
      if (p.y < 0) {
        p.y = h;
        p.x = Math.random() * w;
      }
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, 7);
      ctx.fill();
    });
    fish
      .sort((a, b) => a.z - b.z)
      .forEach((f) => {
        f.x += f.dir * f.sp * (reduce ? 0 : 1.1);
        f.ph += 0.16;
        f.y += Math.sin(t * 0.0008 + f.off) * 0.12;
        const s = (7 + f.z * 17) * (o.scale || 1);
        if (f.dir > 0 && f.x > w + 40) f.x = -40;
        if (f.dir < 0 && f.x < -40) f.x = w + 40;
        drawFish(
          ctx,
          f.x,
          f.y,
          s,
          f.dir,
          f.ph,
          'rgba(' +
            pal.fish +
            ',' +
            ((o.palette === 'dark' ? 0.08 : 0.22) + f.z * (o.palette === 'dark' ? 0.22 : 0.5)).toFixed(2) +
            ')',
        );
      });
    const ae = o.aerators || [0.16, 0.52, 0.86];
    if (!reduce && Math.random() < 0.55) {
      const x = w * ae[Math.floor(Math.random() * ae.length)] + rand(-10, 10);
      bubbles.push({ x, y: h + 4, r: rand(1.4, 4.6), vy: rand(0.5, 1.4), ph: Math.random() * 6 });
    }
    ctx.lineWidth = 1;
    bubbles = bubbles.filter((b) => b.y > h * 0.08);
    bubbles.forEach((b) => {
      b.y -= b.vy;
      b.ph += 0.08;
      const x = b.x + Math.sin(b.ph) * 2.2;
      ctx.strokeStyle = 'rgba(' + pal.bubble + ',.7)';
      ctx.beginPath();
      ctx.arc(x, b.y, b.r, 0, 7);
      ctx.stroke();
      ctx.fillStyle = 'rgba(255,255,255,.5)';
      ctx.beginPath();
      ctx.arc(x - b.r * 0.35, b.y - b.r * 0.35, b.r * 0.3, 0, 7);
      ctx.fill();
    });
  };
}

/** Run a draw function on every animation frame while the canvas is visible (1 fps with reduced motion). */
export function useCanvasLoop(
  ref: RefObject<HTMLCanvasElement>,
  factory: (c: HTMLCanvasElement) => (t: number) => void,
  deps: unknown[] = [],
) {
  const f = useRef(factory);
  f.current = factory;
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const draw = f.current(c);
    const reduce = reduceMotion();
    let visible = true;
    let raf = 0;
    let last = -Infinity;
    const io =
      'IntersectionObserver' in window
        ? new IntersectionObserver((es) => (visible = es[0].isIntersecting), { rootMargin: '100px' })
        : null;
    io?.observe(c);
    draw(0);
    const loop = (t: number) => {
      if (visible && (!reduce || t - last > 1000)) {
        draw(t);
        last = t;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      io?.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export function WaterCanvas({ opts, id, label }: { opts: WaterOpts; id?: string; label?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useCanvasLoop(ref, (c) => makeWater(c, opts));
  return (
    <canvas
      ref={ref}
      id={id}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? 'img' : undefined}
    />
  );
}

export { rand };
