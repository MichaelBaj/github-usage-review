import { useEffect, useState } from "react";
import { api, isDbExportFile, type DbImportMode, type DbImportResult, type ImportResult } from "./api";
import { SummaryTab } from "./components/SummaryTab";
import { TeamsTab } from "./components/TeamsTab";
import { UsersTab } from "./components/UsersTab";
import { QualityTab } from "./components/QualityTab";
// Calendar-date versioning (YYYY-MM-DD)
const VERSION = "2026-06-24";


type Tab = "summary" | "teams" | "users" | "quality";

const TABS: { id: Tab; label: string }[] = [
  { id: "summary", label: "Summary" },
  { id: "quality", label: "Quality & Models" },
  { id: "teams", label: "Teams" },
  { id: "users", label: "Users" },
];

function tabFromHash(): Tab {
  const h = window.location.hash.replace("#", "").split("?")[0] as Tab;
  return TABS.some((t) => t.id === h) ? h : "summary";
}

export function App(): JSX.Element {
  const [tab, setTab] = useState<Tab>(tabFromHash());
  const [refreshing, setRefreshing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [dataVersion, setDataVersion] = useState(0);
  const [lastLoad, setLastLoad] = useState<{ at: string | null; source: string | null; historyDays: number | null }>({
    at: null,
    source: null,
    historyDays: null,
  });
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [dbImportResult, setDbImportResult] = useState<DbImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingDbFile, setPendingDbFile] = useState<File | null>(null);
  const [dbImportMode, setDbImportMode] = useState<DbImportMode>("merge");

  useEffect(() => {
    const onHash = (): void => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    Promise.all([api.kpis({ days: 1 }), api.projections()]).then(([k, p]) =>
      setLastLoad({
        at: k.last_data_load_at ?? k.last_snapshot_at,
        source: k.last_data_load_source ?? (k.last_snapshot_at ? "api" : null),
        historyDays: p.available ? (p.history_days ?? null) : null,
      }),
    ).catch(() => undefined);
  }, [dataVersion]);

  function go(next: Tab): void {
    window.location.hash = next;
    setTab(next);
  }

  async function refresh(): Promise<void> {
    setRefreshing(true);
    setError(null);
      setImportResult(null);
    try {
      await api.runSnapshot();
        setDataVersion((value) => value + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRefreshing(false);
    }
  }

  async function importUsage(file: File | undefined): Promise<void> {
    if (!file) return;
    if (isDbExportFile(file)) {
      importDbExport(file);
      return;
    }
    setImporting(true);
    setError(null);
    setImportResult(null);
    setDbImportResult(null);
    try {
      const result = await api.importFile(file);
      setImportResult(result);
      setDataVersion((value) => value + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setImporting(false);
    }
  }

  function importDbExport(file: File): void {
    setDbImportMode("merge");
    setPendingDbFile(file);
  }

  async function confirmDbImport(): Promise<void> {
    if (!pendingDbFile) return;
    const file = pendingDbFile;
    setPendingDbFile(null);
    setImporting(true);
    setError(null);
    setImportResult(null);
    setDbImportResult(null);
    try {
      const result = await api.importDatabase(file, dbImportMode);
      setDbImportResult(result);
      setDataVersion((value) => value + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setImporting(false);
    }
  }

  async function exportData(): Promise<void> {
    setExporting(true);
    setError(null);
    try {
      await api.exportData();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setExporting(false);
    }
  }

  const lastLoadLabel = lastLoad.at ? `${lastLoad.source ?? "unknown"}: ${lastLoad.at}` : "never";

  return (
    <div className="layout">
      <div className="header">
        <div>
          <h1>Copilot Usage Review</h1>
          <div className="meta">Last data load: {lastLoadLabel}</div>
                    <div className="meta">Version: {VERSION}</div>
          {lastLoad.historyDays != null ? (
            <div className="meta">History collected: {lastLoad.historyDays} days</div>
          ) : null}
        </div>
        <div className="header-actions">
          <button onClick={refresh} disabled={refreshing || importing}>
            {refreshing ? "Refreshing…" : "Refresh snapshot"}
          </button>
          <button onClick={exportData} disabled={exporting || importing || refreshing}>
            {exporting ? "Exporting…" : "Export data"}
          </button>
          <label className={importing || refreshing ? "upload-button upload-disabled" : "upload-button"}>
            {importing ? "Importing…" : "Import file"}
            <input
              type="file"
              accept=".json,.jsonl,.ndjson,.csv,.db,.sqlite,.sqlite3,.gz,application/json,text/csv,application/csv,application/vnd.ms-excel,application/gzip,application/x-sqlite3"
              disabled={importing || refreshing}
              onChange={(event) => {
                void importUsage(event.target.files?.[0]);
                event.currentTarget.value = "";
              }}
            />
          </label>
        </div>
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? "tab tab-active" : "tab"}
            onClick={() => go(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error ? <div className="error">{error}</div> : null}
      {importResult ? (
        <div className="import-note" title={importResult.warnings.join("\n") || undefined}>
          Imported {importResult.rows_imported} rows from {importResult.source_type}
          {importResult.date_range
            ? ` (${importResult.date_range.start} to ${importResult.date_range.end})`
            : ""}
          {importResult.skipped_rows ? `; skipped ${importResult.skipped_rows}` : ""}
          {importResult.warnings.length ? `; ${importResult.warnings.length} warning(s)` : ""}
        </div>
      ) : null}
      {dbImportResult ? (
        <div className="import-note">
          Database import ({dbImportResult.mode}): {dbImportResult.rows_total} rows across{" "}
          {dbImportResult.tables_imported} table(s)
        </div>
      ) : null}

      {tab === "summary" ? <SummaryTab key={`summary-${dataVersion}`} /> : null}
      {tab === "teams" ? <TeamsTab key={`teams-${dataVersion}`} /> : null}
      {tab === "users" ? <UsersTab key={`users-${dataVersion}`} /> : null}
      {tab === "quality" ? <QualityTab key={`quality-${dataVersion}`} /> : null}

      {pendingDbFile ? (
        <div className="modal-overlay" onClick={() => setPendingDbFile(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Import Database Export</h3>
            <p>"{pendingDbFile.name}" is a full database export.</p>
            <fieldset>
              <legend>Import mode</legend>
              <label className="radio-label">
                <input
                  type="radio"
                  name="db-import-mode"
                  value="merge"
                  checked={dbImportMode === "merge"}
                  onChange={() => setDbImportMode("merge")}
                />
                Merge — combine with existing data
              </label>
              <label className="radio-label">
                <input
                  type="radio"
                  name="db-import-mode"
                  value="replace"
                  checked={dbImportMode === "replace"}
                  onChange={() => setDbImportMode("replace")}
                />
                Replace — wipe all current data and load this export
              </label>
            </fieldset>
            <div className="modal-actions">
              <button onClick={() => setPendingDbFile(null)}>Cancel</button>
              <button onClick={() => void confirmDbImport()}>Import</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
