import { useEffect, useState } from "react";
import {
  api,
  isDbExportFile,
  type DbImportMode,
  type DbImportResult,
  type ImportResult,
  type RefreshAllJob,
} from "./api";
import { SummaryTab } from "./components/SummaryTab";
import { TeamsTab } from "./components/TeamsTab";
import { UsersTab } from "./components/UsersTab";
import { QualityTab } from "./components/QualityTab";
import { ImportsExportsTab } from "./components/ImportsExportsTab";
import { defaultWindowThisMonth, type WindowState } from "./components/DateRangeSelector";
// Calendar-date versioning (YYYY-MM-DD.build)
const VERSION = "2026-07-09.1";


type Tab = "summary" | "teams" | "users" | "quality" | "imports-exports";

const TABS: { id: Tab; label: string }[] = [
  { id: "summary", label: "Summary" },
  { id: "quality", label: "Quality & Models" },
  { id: "teams", label: "Teams" },
  { id: "users", label: "Users" },
  { id: "imports-exports", label: "Imports & Exports" },
];

function tabFromHash(): Tab {
  const h = window.location.hash.replace("#", "").split("?")[0] as Tab;
  return TABS.some((t) => t.id === h) ? h : "summary";
}

export function App(): JSX.Element {
  const [tab, setTab] = useState<Tab>(tabFromHash());
  const [win, setWin] = useState<WindowState>(defaultWindowThisMonth());
  const [refreshing, setRefreshing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [dataVersion, setDataVersion] = useState(0);
  const [lastLoad, setLastLoad] = useState<{
    apiAt: string | null;
    csvAt: string | null;
    csvSource: string | null;
    jsonAt: string | null;
    jsonSource: string | null;
    historyDays: number | null;
  }>({
    apiAt: null,
    csvAt: null,
    csvSource: null,
    jsonAt: null,
    jsonSource: null,
    historyDays: null,
  });
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [dbImportResult, setDbImportResult] = useState<DbImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingDbFile, setPendingDbFile] = useState<File | null>(null);
  const [dbImportMode, setDbImportMode] = useState<DbImportMode>("merge");
  const [snapshotDone, setSnapshotDone] = useState<boolean | null>(null); // true=success, false=fail
  const [refreshAllJob, setRefreshAllJob] = useState<RefreshAllJob | null>(null);
  const [refreshAllError, setRefreshAllError] = useState<string | null>(null);
  const [refreshAllNotice, setRefreshAllNotice] = useState<string | null>(null);
  const [notifiedJobId, setNotifiedJobId] = useState<string | null>(null);

  useEffect(() => {
    const onHash = (): void => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    Promise.all([api.kpis({ days: 1 }), api.projections()]).then(([k, p]) =>
      setLastLoad({
        apiAt: k.last_api_load_at ?? k.last_snapshot_at ?? null,
        csvAt: k.last_csv_load_at ?? null,
        csvSource: k.last_csv_load_source ?? null,
        jsonAt: k.last_json_load_at ?? null,
        jsonSource: k.last_json_load_source ?? null,
        historyDays: p.available ? (p.history_days ?? null) : null,
      }),
    ).catch(() => undefined);
  }, [dataVersion]);

  useEffect(() => {
    let disposed = false;
    const poll = async (): Promise<void> => {
      try {
        const job = await api.refreshAllStatus(refreshAllJob?.id);
        if (disposed) return;
        setRefreshAllJob(job);
        if (
          (
            job.status === "completed"
            || job.status === "completed_with_errors"
            || job.status === "failed"
            || job.status === "canceled"
          )
          && notifiedJobId !== job.id
        ) {
          setNotifiedJobId(job.id);
          if (job.status === "completed") {
            setRefreshAllNotice("Refresh all data completed.");
          } else if (job.status === "completed_with_errors") {
            setRefreshAllNotice("Refresh all data completed with errors.");
          } else if (job.status === "canceled") {
            setRefreshAllNotice("Refresh all data canceled.");
          } else {
            setRefreshAllNotice("Refresh all data failed.");
          }
          setDataVersion((value) => value + 1);
        }
      } catch {
        // No active/known job yet.
      }
    };
    void poll();
    if (!refreshAllJob?.id) {
      return () => {
        disposed = true;
      };
    }
    const timer = window.setInterval(() => {
      void poll();
    }, 5000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [refreshAllJob?.id, notifiedJobId]);

  function go(next: Tab): void {
    window.location.hash = next;
    setTab(next);
  }

  async function refresh(): Promise<void> {
    setRefreshing(true);
    setError(null);
    setImportResult(null);
    setSnapshotDone(null);
    try {
      await api.runSnapshot();
      setDataVersion((value) => value + 1);
      setSnapshotDone(true);
      setTimeout(() => setSnapshotDone(null), 5000);
    } catch (e) {
      setError((e as Error).message);
      setSnapshotDone(false);
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

  async function startRefreshAllData(): Promise<void> {
    setRefreshAllError(null);
    try {
      const payload = await api.startRefreshAll({ report_types: ["ai_credit", "detailed"] });
      setRefreshAllJob(payload.job);
      if (payload.started) {
        setRefreshAllNotice("Refresh all data started in background.");
      }
    } catch (e) {
      setRefreshAllError((e as Error).message);
    }
  }

  async function cancelRefreshAllData(): Promise<void> {
    setRefreshAllError(null);
    try {
      const payload = await api.cancelRefreshAll(refreshAllJob?.id);
      setRefreshAllNotice(`Refresh all cancel requested (${payload.job_id}).`);
    } catch (e) {
      setRefreshAllError((e as Error).message);
    }
  }

  async function retryRefreshAllData(): Promise<void> {
    setRefreshAllError(null);
    try {
      const payload = await api.retryRefreshAll({ job_id: refreshAllJob?.id });
      setRefreshAllJob(payload.job);
      setRefreshAllNotice("Refresh all data retried in background.");
    } catch (e) {
      setRefreshAllError((e as Error).message);
    }
  }

  function handleUsageReportImported(result: ImportResult): void {
    setError(null);
    setDbImportResult(null);
    setImportResult(result);
    setDataVersion((value) => value + 1);
  }

  const apiLabel = lastLoad.apiAt ? lastLoad.apiAt : "never";
  const csvLabel = lastLoad.csvAt ? lastLoad.csvAt : "never";
  const jsonLabel = lastLoad.jsonAt ? lastLoad.jsonAt : "never";

  return (
    <div className="layout">
      <div className="header">
        <div>
          <h1>Copilot Usage Review</h1>
          <table className="meta-table">
            <tbody>
              <tr><td>Version:</td><td>{VERSION}</td></tr>
              {lastLoad.historyDays != null ? (
                <tr><td>History collected:</td><td>{lastLoad.historyDays} days</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
        {refreshAllJob ? (
          <button className="refresh-chip" onClick={() => go("imports-exports")}>
            Refresh All: {refreshAllJob.status}
          </button>
        ) : null}
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

      {refreshAllNotice ? (
        <div className="global-notice" onClick={() => setRefreshAllNotice(null)} role="status">
          {refreshAllNotice}
        </div>
      ) : null}

      {tab === "summary" ? <SummaryTab key={`summary-${dataVersion}`} win={win} onWinChange={setWin} /> : null}
      {tab === "teams" ? <TeamsTab key={`teams-${dataVersion}`} win={win} onWinChange={setWin} /> : null}
      {tab === "users" ? <UsersTab key={`users-${dataVersion}`} win={win} onWinChange={setWin} /> : null}
      {tab === "quality" ? <QualityTab key={`quality-${dataVersion}`} win={win} onWinChange={setWin} /> : null}
      {tab === "imports-exports" ? (
        <ImportsExportsTab
          apiLabel={apiLabel}
          csvLabel={csvLabel}
          jsonLabel={jsonLabel}
          csvSource={lastLoad.csvSource}
          jsonSource={lastLoad.jsonSource}
          refreshing={refreshing}
          importing={importing}
          exporting={exporting}
          snapshotDone={snapshotDone}
          error={error}
          importResult={importResult}
          dbImportResult={dbImportResult}
          onRefresh={refresh}
          onExport={exportData}
          onImport={importUsage}
          onUsageReportImported={handleUsageReportImported}
          refreshAllJob={refreshAllJob}
          refreshAllError={refreshAllError}
          onStartRefreshAll={startRefreshAllData}
          onCancelRefreshAll={cancelRefreshAllData}
          onRetryRefreshAll={retryRefreshAllData}
        />
      ) : null}

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
