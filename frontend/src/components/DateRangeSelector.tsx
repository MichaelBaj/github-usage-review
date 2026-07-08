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

const PRESETS: { label: string; days: number }[] = [
  { label: "7d", days: 7 },
  { label: "30d", days: 30 },
  { label: "60d", days: 60 },
  { label: "90d", days: 90 },
];

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function isoDaysAgo(n: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n + 1);
  return d.toISOString().slice(0, 10);
}

function firstOfMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function lastOfMonth(): string {
  const d = new Date();
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0);
  return last.toISOString().slice(0, 10);
}

/** Date-range selector with preset shortcuts and custom from/to inputs. */
export function DateRangeSelector({ value, onChange }: Props): JSX.Element {
  const [local, setLocal] = useState(value);
  useEffect(() => setLocal(value), [value]);

  function applyPreset(days: number): void {
    const next: WindowState = { days, preset: undefined, start: isoDaysAgo(days), end: todayIso() };
    onChange(next);
  }

  function applyThisMonth(): void {
    const next: WindowState = { days: null, preset: "month", start: firstOfMonth(), end: lastOfMonth() };
    onChange(next);
  }

  function applyCustom(): void {
    onChange({ days: null, preset: undefined, start: local.start, end: local.end });
  }

  return (
    <div className="window-bar">
      <span className="window-label">Window:</span>
      <button
        className={value.preset === "month" ? "chip chip-on" : "chip"}
        onClick={applyThisMonth}
      >
        This month
      </button>
      {PRESETS.map((p) => (
        <button
          key={p.label}
          className={value.days === p.days && !value.preset ? "chip chip-on" : "chip"}
          onClick={() => applyPreset(p.days)}
        >
          {p.label}
        </button>
      ))}
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
  return { days: null, preset: "month", start: firstOfMonth(), end: lastOfMonth() };
}

/** Convenience: build the initial window state (last N days). */
export function defaultWindow(days = 30): WindowState {
  return { days, start: isoDaysAgo(days), end: todayIso() };
}

/** Convert WindowState to the params expected by the API client. */
export function toWindowParams(w: WindowState): { start: string; end: string } {
  return { start: w.start, end: w.end };
}
