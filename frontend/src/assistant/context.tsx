import { createContext, useContext } from 'react';

export interface AssistantApi {
  open: () => void;
  close: () => void;
  toggle: () => void;
  ask: (q: string) => void;
  isOpen: boolean;
}

export const AssistantCtx = createContext<AssistantApi>({
  open: () => undefined,
  close: () => undefined,
  toggle: () => undefined,
  ask: () => undefined,
  isOpen: false,
});

export const useAssistant = () => useContext(AssistantCtx);
