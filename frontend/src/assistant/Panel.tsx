import { useMemo, useState, type ReactNode } from 'react';
import { AssistantCtx } from './context';

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const value = useMemo(
    () => ({ isOpen, open: () => setOpen(true), close: () => setOpen(false), toggle: () => setOpen((o) => !o), ask: () => setOpen(true) }),
    [isOpen],
  );
  return <AssistantCtx.Provider value={value}>{children}</AssistantCtx.Provider>;
}
