import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type CSSProperties,
  type InputHTMLAttributes,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  type RefObject,
  type TextareaHTMLAttributes,
} from 'react';
import { createPortal } from 'react-dom';
import { Icon } from '../icons';
import { clamp, cx, modKey } from '../lib/format';
import { dismissToast, useStore } from '../store';
import { errorText } from '../lib/format';

/* ─────────────────────────────────── buttons ─────────────────────────────────── */

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
  icon?: string;
  iconRight?: string;
  busy?: boolean;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  iconRight,
  busy,
  className,
  children,
  disabled,
  type,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type ?? 'button'}
      className={cx('btn', `btn-${variant}`, `btn-${size}`, className)}
      disabled={disabled || busy}
      {...rest}
    >
      {busy ? <Spinner size={14} /> : icon ? <Icon name={icon} size={size === 'sm' ? 14 : 15} /> : null}
      {children !== undefined && children !== null && <span className="btn-label">{children}</span>}
      {iconRight && <Icon name={iconRight} size={14} />}
    </button>
  );
}

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  icon: string;
  label: string;
  size?: number;
  active?: boolean;
  tip?: boolean;
}

export function IconButton({ icon, label, size = 16, active, tip = true, className, type, ...rest }: IconButtonProps) {
  return (
    <button
      type={type ?? 'button'}
      className={cx('icon-btn', active && 'active', className)}
      aria-label={label}
      data-tip={tip ? label : undefined}
      {...rest}
    >
      <Icon name={icon} size={size} />
    </button>
  );
}

export function Spinner({ size = 16, className }: { size?: number; className?: string }) {
  return <Icon name="loader" size={size} className={cx('spin', className)} />;
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}

/* ─────────────────────────────────── inputs ──────────────────────────────────── */

interface TextInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size' | 'onChange'> {
  label?: string;
  placeholder?: string;
  value: string;
  mono?: boolean;
  autoFocus?: boolean;
  inputMode?: InputHTMLAttributes<HTMLInputElement>['inputMode'];
  onChange: (value: string) => void;
}

export function TextInput({ label, placeholder, value, mono, autoFocus, inputMode, onChange, className, ...rest }: TextInputProps) {
  return (
    <label className={cx('field', label && 'has-label', className)}>
      {label && <span className="field-label">{label}</span>}
      <input
        className={cx('text-input', mono && 'mono')}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoFocus={autoFocus}
        inputMode={inputMode}
        {...rest}
      />
    </label>
  );
}

interface TextAreaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'size' | 'onChange'> {
  label?: string;
  placeholder?: string;
  value: string;
  rows?: number;
  mono?: boolean;
  onChange: (value: string) => void;
}

export function TextArea({ label, placeholder, value, rows = 6, mono, onChange, className, ...rest }: TextAreaProps) {
  return (
    <label className={cx('field', label && 'has-label', className)}>
      {label && <span className="field-label">{label}</span>}
      <textarea
        className={cx('text-area', mono && 'mono')}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        {...rest}
      />
    </label>
  );
}

interface SwitchProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export function Switch({ label, checked, onChange, disabled }: SwitchProps) {
  return (
    <label className={cx('switch', disabled && 'disabled')}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch-thumb" />
      <span className="switch-label">{label}</span>
    </label>
  );
}

/* ─────────────────────────────────── select ──────────────────────────────────── */

interface SelectOption {
  value: string;
  label: string;
  description?: string;
  icon?: string;
}

interface SelectProps {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  label?: string;
  hint?: string;
}

export function Select({ value, options, onChange, label, hint }: SelectProps) {
  return (
    <label className={cx('field', label && 'has-label')}>
      {label && <span className="field-label">{label}</span>}
      <select className="select" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {hint && <small className="hint">{hint}</small>}
    </label>
  );
}

/* ─────────────────────────────────── number input ───────────────────────────── */

interface NumberInputProps {
  label?: string;
  value: number | null;
  min?: number;
  max?: number;
  allowEmpty?: boolean;
  placeholder?: string;
  onCommit: (value: number | null) => void;
}

export function NumberInput({ label, value, min, max, allowEmpty, placeholder, onCommit }: NumberInputProps) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value === null ? '' : String(value));

  const commit = () => {
    const n = text === '' || text === null ? null : Number(text);
    if (Number.isNaN(n)) return;
    const clamped = clamp(n, min ?? -Infinity, max ?? Infinity, n ?? 0);
    onCommit(clamped);
    setEditing(false);
  };

  return (
    <label className={cx('field', label && 'has-label')}>
      {label && <span className="field-label">{label}</span>}
      <input
        className="number-input"
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit();
          if (e.key === 'Escape') { setText(value === null ? '' : String(value)); setEditing(false); }
        }}
        onFocus={() => setEditing(true)}
        onDoubleClick={() => setEditing(true)}
        placeholder={placeholder}
        inputMode="numeric"
        {...(editing ? {} : { readOnly: true })}
      />
    </label>
  );
}

/* ─────────────────────────────────── segmented ───────────────────────────────── */

interface SegmentedProps {
  value: string;
  options: { value: string; label: string; icon?: string; tip?: string }[];
  onChange: (value: string) => void;
}

export function Segmented({ value, options, onChange }: SegmentedProps) {
  return (
    <div className="segmented">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={cx('seg-btn', value === o.value && 'on')}
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
        >
          {o.icon && <Icon name={o.icon} size={13} />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ─────────────────────────────────── modal ───────────────────────────────────── */

interface ModalProps {
  title: string;
  onClose: () => void;
  width?: number;
  children: ReactNode;
  footer?: ReactNode;
}

export function Modal({ title, onClose, width = 520, children, footer }: ModalProps) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={{ width }}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            <Icon name="x" size={16} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}

/* ─────────────────────────────────── popover ─────────────────────────────────── */

export type Placement = 'bottom-start' | 'bottom-end' | 'top-start' | 'top-end' | 'right-start';

interface PopoverProps {
  open: boolean;
  onClose: () => void;
  anchor: RefObject<HTMLElement | null> | { x: number; y: number };
  placement?: Placement;
  offset?: number;
  className?: string;
  children: ReactNode;
}

function anchorRect(anchor: PopoverProps['anchor']): DOMRect | null {
  if ('x' in anchor) return new DOMRect(anchor.x, anchor.y, 0, 0);
  return anchor.current ? anchor.current.getBoundingClientRect() : null;
}

export function Popover({ open, onClose, anchor, placement = 'bottom-start', offset = 6, className, children }: PopoverProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ left: number; top: number; minWidth?: number; maxHeight: number } | null>(null);

  useLayoutEffect(() => {
    if (!open) { setPosition(null); return; }
    const rect = anchorRect(anchor);
    if (!rect) { setPosition(null); return; }
    let left = rect.left;
    let top = rect.bottom + offset;
    if (placement === 'bottom-end') left = rect.right - (ref.current?.offsetWidth ?? 0);
    setPosition({ left, top, minWidth: rect.width, maxHeight: window.innerHeight - rect.bottom - offset });
  }, [open, anchor, placement, offset]);

  if (!open) return null;
  return createPortal(
    <div className={cx('popover', className)} style={{ position: 'fixed', left: position?.left ?? 0, top: position?.top ?? 0, minWidth: position?.minWidth }}>
      {children}
    </div>,
    document.body,
  );
}

interface MenuItemProps {
  icon?: string;
  label: string;
  hint?: string;
  danger?: boolean;
  onSelect: () => void;
  checked?: boolean;
  description?: string;
}

export function MenuItem({ icon, label, hint, danger, onSelect, checked, description }: MenuItemProps) {
  return (
    <button type="button" className={cx('menu-item', danger && 'danger', checked && 'checked')} onClick={(e) => { e.stopPropagation(); onSelect(); }}>
      {icon && <span className="menu-item-icon"><Icon name={icon} size={14} /></span>}
      <span className="menu-item-label">{label}</span>
      {checked && <span className="menu-item-check"><Icon name="check" size={14} /></span>}
      {hint && <span className="menu-item-hint">{hint}</span>}
      {description && <span className="menu-item-desc">{description}</span>}
    </button>
  );
}

export function MenuSeparator() {
  return <div className="menu-separator" />;
}

export function Dropdown({ placement, trigger, children }: { placement: Placement; trigger: (props: { onClose: () => void }) => ReactNode; children: (close: () => void) => ReactNode }) {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement>(null);
  return (
    <div style={{ display: 'inline-block', position: 'relative' }}>
      {trigger({ onClose: () => setOpen(false) })}
      <Popover open={open} onClose={() => setOpen(false)} anchor={anchorRef} placement={placement}>
        {children(() => setOpen(false))}
      </Popover>
    </div>
  );
}

/* ─────────────────────────────────── toasts ──────────────────────────────────── */

export function Toasts() {
  const toasts = useStore((s) => s.toasts);
  return (
    <div className="toasts">
      {toasts.map((t) => (
        <div key={t.id} className={cx('toast', `toast-${t.kind}`)}>
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );
}

export function TooltipLayer() {
  return <div className="tooltip-layer" />;
}

export function Resizer({ edge, value, min, max, onChange, onCommit }: { edge: 'left' | 'right'; value: number; min: number; max: number; onChange: (v: number) => void; onCommit: (v: number) => void }) {
  return <div className={`resizer resizer-${edge}`} />;
}

export { errorText };
