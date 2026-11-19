// Small building blocks of the prototype: badge, toast, modal, side sheet, validated fields.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from 'react';
import { cap } from '../lib/format';

export const Badge = ({ st }: { st: string }) => <span className={`badge b-${st}`}>{cap(st)}</span>;
export const sevClass = (s: string) => (s === 'high' || s === 'critical' ? 'b-critical' : s === 'medium' ? 'b-warning' : 'b-info');

/* ---------- toasts (bottom centre, 4.2 s) ---------- */
type Toast = { id: number; node: ReactNode };
const ToastCtx = createContext<(node: ReactNode) => void>(() => undefined);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<Toast[]>([]);
  const push = useCallback((node: ReactNode) => {
    const id = Date.now() + Math.random();
    setList((l) => [...l, { id, node }]);
    window.setTimeout(() => setList((l) => l.filter((t) => t.id !== id)), 4200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" id="toasts" aria-live="polite">
        {list.map((t) => (
          <div className="toast" key={t.id}>
            {t.node}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

/* ---------- Escape closes the top-most overlay ---------- */
function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', h);
    return () => document.removeEventListener('keydown', h);
  }, [open, onClose]);
}

function useFocusFirst(open: boolean, sel: string) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const t = window.setTimeout(() => (ref.current?.querySelector(sel) as HTMLElement | null)?.focus(), 30);
    return () => {
      window.clearTimeout(t);
      prev?.focus?.();
    };
  }, [open, sel]);
  return ref;
}

export function Modal({ open, onClose, children, label }: { open: boolean; onClose: () => void; children: ReactNode; label?: string }) {
  useEscape(open, onClose);
  const ref = useFocusFirst(open, 'input, textarea, button');
  return (
    <div className={`modal-bg${open ? ' open' : ''}`} id="modalBg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      {open && (
        <div className="modal" role="dialog" aria-modal="true" aria-label={label} id="modal" ref={ref}>
          {children}
        </div>
      )}
    </div>
  );
}

export function Sheet({ open, onClose, children, label }: { open: boolean; onClose: () => void; children: ReactNode; label?: string }) {
  useEscape(open, onClose);
  const ref = useFocusFirst(open, 'input, button');
  return (
    <div className={`sheet-bg${open ? ' open' : ''}`} id="sheetBg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      {open && (
        <div className="sheet" id="sheet" role="dialog" aria-modal="true" aria-label={label || 'Details'} ref={ref}>
          {children}
        </div>
      )}
    </div>
  );
}

/* ---------- validation: on blur only after typing, on submit; cleared as soon as fixed ---------- */
type Rule = { required?: boolean; email?: boolean; min?: number };
type FormApi = {
  errors: Record<string, string>;
  register: (name: string, rule: Rule) => void;
  touch: (name: string, value: string) => void;
  blur: (name: string, value: string) => void;
};
const FormCtx = createContext<FormApi | null>(null);

export function check(value: string, rule: Rule): string {
  const v = value.trim();
  if (rule.required && !v) return 'Fill in this field.';
  if (rule.email && v && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) return 'Enter an email like name@farm.com.';
  if (rule.min && v.length < rule.min) return `Use at least ${rule.min} characters.`;
  return '';
}

export function ValidatedForm({
  onValid,
  children,
  className = 'stack',
  setError,
}: {
  onValid: (data: Record<string, string>, form: HTMLFormElement) => void;
  children: ReactNode;
  className?: string;
  setError?: (fn: (name: string, msg: string) => void) => void;
}) {
  const rules = useRef<Record<string, Rule>>({});
  const dirty = useRef<Set<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const setErr = useCallback((name: string, msg: string) => setErrors((e) => ({ ...e, [name]: msg })), []);
  useEffect(() => setError?.(setErr), [setError, setErr]);
  const api: FormApi = {
    errors,
    register: (name, rule) => {
      rules.current[name] = rule;
    },
    touch: (name, value) => {
      dirty.current.add(name);
      if (errors[name]) setErr(name, check(value, rules.current[name] || {}));
    },
    blur: (name, value) => {
      if (dirty.current.has(name)) setErr(name, check(value, rules.current[name] || {}));
    },
  };
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = e.currentTarget;
    const data = Object.fromEntries(new FormData(f).entries()) as Record<string, string>;
    const next: Record<string, string> = {};
    for (const [name, rule] of Object.entries(rules.current)) next[name] = check(data[name] ?? '', rule);
    setErrors(next);
    if (Object.values(next).some(Boolean)) return;
    onValid(data, f);
  };
  return (
    <FormCtx.Provider value={api}>
      <form className={className} noValidate onSubmit={submit}>
        {children}
      </form>
    </FormCtx.Provider>
  );
}

type FieldProps = {
  name: string;
  label: ReactNode;
  id: string;
  rule?: Rule;
  textarea?: boolean;
  password?: boolean;
} & InputHTMLAttributes<HTMLInputElement> &
  TextareaHTMLAttributes<HTMLTextAreaElement>;

export function Field({ name, label, id, rule = {}, textarea, password, ...rest }: FieldProps) {
  const f = useContext(FormCtx)!;
  f.register(name, rule);
  const err = f.errors[name] || '';
  const [show, setShow] = useState(false);
  const common = {
    id,
    name,
    required: rule.required,
    onInput: (e: FormEvent<HTMLInputElement | HTMLTextAreaElement>) => f.touch(name, e.currentTarget.value),
    onBlur: (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => f.blur(name, e.currentTarget.value),
    'aria-invalid': err ? true : undefined,
    'aria-describedby': err ? id + '-err' : undefined,
  };
  return (
    <label className={`field${err ? ' invalid' : ''}`} htmlFor={id}>
      {label}
      {textarea ? (
        <textarea {...(rest as TextareaHTMLAttributes<HTMLTextAreaElement>)} {...common} />
      ) : password ? (
        <span className="pw">
          <input {...(rest as InputHTMLAttributes<HTMLInputElement>)} {...common} type={show ? 'text' : 'password'} />
          <button type="button" onClick={() => setShow(!show)}>
            {show ? 'Hide' : 'Show'}
          </button>
        </span>
      ) : (
        <input {...(rest as InputHTMLAttributes<HTMLInputElement>)} {...common} />
      )}
      <span className="err" id={id + '-err'}>
        {err}
      </span>
    </label>
  );
}
