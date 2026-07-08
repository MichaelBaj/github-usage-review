import { useEffect, useState } from "react";

export interface WindowState {
  days: number | null;
  preset?: string;
  start: string;
  end: string;
}

interface Props {
  value: WindowState;
  onChange: (next: WindowState) => void;
}

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function monthStart(year: number, month: number): string {
  return `${year}-${String(month + 1).padStart(2, "0")}-01`;
}

function monthEnd(year: number, month: number): string {
  const last = new Date(year, month + 1, 0);
  return last.toISOString().slice(0, 10);
}

function monthPresetKey(year: number, month: number): string {
  return `month-${year}-${String(month + 1).padStart(2, "0")}`;
}

/** Date-range selector with month buttons and custom from/to inputs. */
export function DateRangeSelector({ value, onChange }: Props): JSX.Element {
  const [local, setLocal] = useState(value);
  useEffect(() => setLocal(value), [value]);

  const now = new Date();
  const currentYear = now.getFullYear();

  function applyMonth(month: number): void {
    const next: WindowState = {
      days: null,
      preset: monthPresetKey(currentYear, month),
      start: monthStart(currentYear, month),
      end: monthEnd(currentYear, month),
    };
    onChange(next);
  }

  function applyCustom(): void {
    onChange({ days: null, preset: undefined, start: local.start, end: local.end });
  }

  return (
    <div className="window-bar">
      <span className="window-label">Window:</span>
      {MONTH_LABELS.map((label, idx) => (
        <button
          key={label}
          className={value.preset === monthPresetKey(currentYear, idx) ? "chip chip-on" : "chip"}
          onClick={() => applyMonth(idx)}
        >
          {label}
        </button>
      ))}
      <span className="window-divider">|</span>
      <input
        type="date"
        value={local.start}
        onChange={(e) => setLocal({ ...local, start: e.target.value, days: null, preset: undefined })}
      />
      <span>→</span>
      <input
        type="date"
        value={local.end}
        onChange={(e) => setLocal({ ...local, end: e.target.value, days: null, preset: undefined })}
      />
      <button onClick={applyCustom} className="chip">
        Apply
      </button>
      <span className="window-summary">
        {value.start} → {value.end}
      </span>
    </div>
  );
}

/** Convenience: build a window state for the current calendar month (default). */
export function defaultWindowThisMonth(): WindowState {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  return { days: null, preset: monthPresetKey(year, month), start: monthStart(year, month), end: monthEnd(year, month) };
}

/** Convenience: build the initial window state (last N days). */
export function defaultWindow(_days = 30): WindowState {
  return defaultWindowThisMonth();
}

/** Convert WindowState to the params expected by the API client. */
export function toWindowParams(w: WindowState): { start: string; end: string } {
  return { start: w.start, end: w.end };
}
