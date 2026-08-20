import { useEffect, useState } from "react";
import {
  api,
  isDbExportFile,
  type DbImportMode,
  type DbImportResult,
  type ImportResult,
} from "./api";
import { SummaryTab } from "./components/SummaryTab";
import { TeamsTab } from "./components/TeamsTab";
import { UsersTab } from "./components/UsersTab";
import { QualityTab } from "./components/QualityTab";
import { ImportsExportsTab } from "./components/ImportsExportsTab";
import { defaultWindowThisMonth, type WindowState } from "./components/DateRangeSelector";
// Calendar-date versioning (YYYY-MM-DD.build)
const VERSION = "2026-08-20.3";


type Tab = "summary" | "teams" | "users" | "quality" | "imports-exports";

const PUBLIC_TABS: { id: Tab; label: string }[] = [
  { id: "summary", label: "Summary" },
  { id: "quality", label: "Quality & Models" },
  { id: "teams", label: "Teams" },
  { id: "users", label: "Users" },
];

function parseHash(): { tab: string; adminToken: string } {
  const raw = window.location.hash.replace("#", "");
  const [path, query] = raw.split("?");
  const params = new URLSearchParams(query ?? "");
  return { tab: path, adminToken: params.get("admin") ?? "" };
}

function tabFromHash(isAdmin: boolean): Tab {
  const { tab } = parseHash();
  const allTabs: Tab[] = isAdmin
    ? [...PUBLIC_TABS.map((t) => t.id), "imports-exports"]
    : PUBLIC_TABS.map((t) => t.id);
  return allTabs.includes(tab as Tab) ? (tab as Tab) : "summary";
}

export function App(): JSX.Element {
  const [isAdmin, setIsAdmin] = useState(false);
  const [adminToken, setAdminToken] = useState("");
  const [tab, setTab] = useState<Tab>("summary");
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
    apiJsonAt: string | null;
    exportNdjsonAt: string | null;
    copilotUsageInsightAt: string | null;
    csvUsageReportAt: string | null;
    csvAiUsageReportAt: string | null;
    dbExportAt: string | null;
    dbExportSource: string | null;
    historyDays: number | null;
  }>({
    apiAt: null,
    csvAt: null,
    csvSource: null,
    jsonAt: null,
    jsonSource: null,
    apiJsonAt: null,
    exportNdjsonAt: null,
    copilotUsageInsightAt: null,
    csvUsageReportAt: null,
    csvAiUsageReportAt: null,
    dbExportAt: null,
    dbExportSource: null,
    historyDays: null,
  });
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [dbImportResult, setDbImportResult] = useState<DbImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingDbFile, setPendingDbFile] = useState<File | null>(null);
  const [dbImportMode, setDbImportMode] = useState<DbImportMode>("merge");
  const [snapshotDone, setSnapshotDone] = useState<boolean | null>(null);

  // Validate admin token from URL hash on mount
  useEffect(() => {
    const { adminToken: token } = parseHash();
    if (!token) return;
    api.validateAdminToken(token).then((valid) => {
      if (valid) {
        setIsAdmin(true);
        setAdminToken(token);
        setTab(tabFromHash(true));
      }
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    const onHash = (): void => setTab(tabFromHash(isAdmin));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [isAdmin]);

  useEffect(() => {
    Promise.all([api.kpis({ days: 1 }), api.projections()]).then(([k, p]) =>
      setLastLoad({
        apiAt: k.last_api_load_at ?? k.last_snapshot_at ?? null,
        csvAt: k.last_csv_load_at ?? null,
        csvSource: k.last_csv_load_source ?? null,
        jsonAt: k.last_json_load_at ?? null,
        jsonSource: k.last_json_load_source ?? null,
        apiJsonAt: k.last_api_json_load_at ?? null,
        exportNdjsonAt: k.last_github_export_ndjson_load_at ?? null,
        copilotUsageInsightAt: k.last_copilot_usage_insight_ndjson_load_at ?? null,
        csvUsageReportAt: k.last_csv_usage_report_load_at ?? null,
        csvAiUsageReportAt: k.last_csv_ai_usage_report_load_at ?? null,
        dbExportAt: k.last_db_export_load_at ?? null,
        dbExportSource: k.last_db_export_load_source ?? null,
        historyDays: p.available ? (p.history_days ?? null) : null,
      }),
    ).catch(() => undefined);
  }, [dataVersion]);

  function go(next: Tab): void {
    if (next === "imports-exports" && isAdmin) {
      window.location.hash = `${next}?admin=${adminToken}`;
    } else {
      window.location.hash = next;
    }
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

  async function importUsage(file: File | undefined, sourceHint?: string): Promise<void> {
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
      const result = await api.importFile(file, adminToken, sourceHint);
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
      const result = await api.importDatabase(file, dbImportMode, adminToken);
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
      await api.exportData(adminToken);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setExporting(false);
    }
  }

  function handleUsageReportImported(result: ImportResult): void {
    setError(null);
    setDbImportResult(null);
    setImportResult(result);
    setDataVersion((value) => value + 1);
  }

  const dataLoadEntries: Array<{ name: string; dataType: string; lastLoaded: string; source: string }> = [
    { name: "GitHub API Snapshot", dataType: "API", lastLoaded: lastLoad.apiAt ?? "never", source: "api" },
    { name: "Copilot Usage Insight", dataType: "NDJSON", lastLoaded: lastLoad.copilotUsageInsightAt ?? "never", source: "copilot_usage_insight_ndjson" },
    { name: "Code Generation Insight", dataType: "NDJSON", lastLoaded: lastLoad.exportNdjsonAt ?? "never", source: "github_export_ndjson" },
    { name: "Metered Usage Billing", dataType: "CSV", lastLoaded: lastLoad.csvUsageReportAt ?? "never", source: "csv_usage_report" },
    { name: "AI Usage Billing", dataType: "CSV", lastLoaded: lastLoad.csvAiUsageReportAt ?? "never", source: "csv_ai_usage_report" },
    { name: "Copilot Usage Export", dataType: "DB", lastLoaded: lastLoad.dbExportAt ?? "never", source: lastLoad.dbExportSource ?? "db-export" },
  ];

  const visibleTabs = isAdmin
    ? [...PUBLIC_TABS, { id: "imports-exports" as Tab, label: "Imports & Exports" }]
    : PUBLIC_TABS;

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
      </div>

      <div className="tabs">
        {visibleTabs.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? "tab tab-active" : "tab"}
            onClick={() => go(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "summary" ? <SummaryTab key={`summary-${dataVersion}`} win={win} onWinChange={setWin} /> : null}
      {tab === "teams" ? <TeamsTab key={`teams-${dataVersion}`} win={win} onWinChange={setWin} /> : null}
      {tab === "users" ? <UsersTab key={`users-${dataVersion}`} win={win} onWinChange={setWin} /> : null}
      {tab === "quality" ? <QualityTab key={`quality-${dataVersion}`} win={win} onWinChange={setWin} /> : null}
      {tab === "imports-exports" && isAdmin ? (
        <ImportsExportsTab
          dataLoadEntries={dataLoadEntries}
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
