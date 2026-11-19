// Icons from the prototype (24x24 stroke icons) and the fish logo.

const ICONS: Record<string, string> = {
  overview: '<path d="M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z"/>',
  basins: '<path d="M3 9c3 2 6 2 9 0s6-2 9 0M3 14c3 2 6 2 9 0s6-2 9 0M3 19c3 2 6 2 9 0s6-2 9 0"/>',
  alerts: '<path d="M6 16v-5a6 6 0 1 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0"/>',
  reports: '<path d="M4 6h16v12H4zM4 13h5l1 2h4l1-2h5"/>',
  team: '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><circle cx="17" cy="9" r="2.5"/><path d="M15.5 14.2c3 .2 5.5 2.6 5.5 5.8"/>',
  shift: '<path d="M8 4h8v3H8zM6 6H5v15h14V6h-1M9 12h6M9 16h4"/>',
  sensors:
    '<circle cx="12" cy="12" r="2"/><path d="M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8"/>',
  maintenance: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17l3 3 5.3-5.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.5-.5-.5-2.5z"/>',
  gauge: '<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4-6"/>',
  fish: '<path d="M3 12c3-4.5 9-4.5 12 0-3 4.5-9 4.5-12 0z"/><path d="M15 12l5-3.5v7z"/>',
  euro: '<path d="M17 6.5A6 6 0 1 0 17 17.5M4 10h9M4 14h9"/>',
  chat: '<path d="M4 12c3-4.5 9-4.5 12 0-3 4.5-9 4.5-12 0z"/><path d="M16 12l4-3v6z"/>',
  ops: '<path d="M4 19V5M4 19h16M8 15l3-4 3 2 5-6"/>',
};

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: ICONS[name] }}
    />
  );
}

export function FishSvg() {
  return (
    <svg viewBox="0 0 30 20" aria-hidden="true">
      <path d="M2 10c5-7.4 14-7.4 19 0-5 7.4-14 7.4-19 0z" fill="currentColor" />
      <path d="M20.5 10 28 4.2v11.6z" fill="currentColor" />
    </svg>
  );
}

export function BrandSvg({ eye = '#fff' }: { eye?: string }) {
  return (
    <svg viewBox="0 0 30 20" aria-hidden="true">
      <path d="M2 10c5-7.4 14-7.4 19 0-5 7.4-14 7.4-19 0z" fill="currentColor" />
      <path d="M20.5 10 28 4.2v11.6z" fill="currentColor" />
      <circle cx="7.6" cy="9" r="1.5" fill={eye} />
    </svg>
  );
}

export function Check() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}

export function CheckSm() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}
