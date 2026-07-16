import { useEffect, useState } from "react";

import {
  api,
  type DbImportResult,
  type ImportResult,
  type RefreshAllJob,
  type UsageReportExport,
  type UsageReportType,
} from "../api";

interface ImportsExportsTabProps {
  apiLabel: string;
  csvLabel: string;
  jsonLabel: string;
  csvSource: string | null;
  jsonSource: string | null;
  refreshing: boolean;
  importing: boolean;
  exporting: boolean;
  snapshotDone: boolean | null;
  error: string | null;
  importResult: ImportResult | null;
  dbImportResult: DbImportResult | null;
  onRefresh: () => Promise<void>;
  onExport: () => Promise<void>;
  onImport: (file: File | undefined) => Promise<void>;
  onUsageReportImported: (result: ImportResult) => void;
  refreshAllJob: RefreshAllJob | null;
  refreshAllError: string | null;
  onStartRefreshAll: () => Promise<void>;
  onCancelRefreshAll: () => Promise<void>;
  onRetryRefreshAll: () => Promise<void>;
}

function usageReportAccessHint(error: string | null): string | null {
  if (!error) return null;
  const text = error.toLowerCase();
  if (!(text.includes("usage report") || text.includes("usage-reports"))) return null;
  const slugMatch = error.match(/configured enterprise slug:\s*'([^']*)'/i);
  const configuredSlug = slugMatch?.[1]?.trim() || null;
  if (text.includes("(403)") || text.includes("forbidden")) {
    return (
      "403 from GitHub usage-reports API. Verify account is enterprise owner or enterprise billing manager, " +
      "and token has enterprise billing scope (classic PAT: manage_billing:enterprise)."
    );
  }
  if (text.includes("(404)") || text.includes("not found")) {
    const slugHint = configuredSlug
      ? `configured enterprise slug is '${configuredSlug}', `
      : "configured enterprise slug is correct, ";
    return (
      `404 from GitHub usage-reports API. Verify ${slugHint}enterprise role, ` +
      "and that usage-report exports are enabled for this enterprise plan."
    );
  }
  return null;
}

export function ImportsExportsTab({
  apiLabel,
  csvLabel,
  jsonLabel,
  csvSource,
  jsonSource,
  refreshing,
  importing,
  exporting,
  snapshotDone,
  error,
  importResult,
  dbImportResult,
  onRefresh,
  onExport,
  onImport,
  onUsageReportImported,
  refreshAllJob,
  refreshAllError,
  onStartRefreshAll,
  onCancelRefreshAll,
  onRetryRefreshAll,
}: ImportsExportsTabProps): JSX.Element {
  const [reports, setReports] = useState<UsageReportExport[]>([]);
  const [reportsLoading, setReportsLoading] = useState(false);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const [creatingReport, setCreatingReport] = useState(false);
  const [downloadingReportId, setDownloadingReportId] = useState<string | null>(null);
  const [importingReportId, setImportingReportId] = useState<string | null>(null);
  const [reportType, setReportType] = useState<UsageReportType>("ai_credit");
  const [sendEmail, setSendEmail] = useState(false);
  const [startDate, setStartDate] = useState<string>(() => {
    const now = new Date();
    const y = now.getUTCFullYear();
    const m = String(now.getUTCMonth() + 1).padStart(2, "0");
    return `${y}-${m}-01`;
  });
  const [endDate, setEndDate] = useState<string>(() => {
    const now = new Date();
    const y = now.getUTCFullYear();
    const m = String(now.getUTCMonth() + 1).padStart(2, "0");
    const d = String(now.getUTCDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  });

  async function loadReports(): Promise<void> {
    setReportsLoading(true);
    setReportsError(null);
    try {
      const payload = await api.listUsageReports();
      setReports(payload.exports);
    } catch (e) {
      setReportsError((e as Error).message);
    } finally {
      setReportsLoading(false);
    }
  }

  async function createReport(): Promise<void> {
    if (!startDate || !endDate) {
      setReportsError("start and end date are required");
      return;
    }
    setCreatingReport(true);
    setReportsError(null);
    try {
      await api.createUsageReport({
        report_type: reportType,
        start_date: startDate,
        end_date: endDate,
        send_email: sendEmail,
      });
      await loadReports();
    } catch (e) {
      setReportsError((e as Error).message);
    } finally {
      setCreatingReport(false);
    }
  }

  async function downloadReport(reportId: string): Promise<void> {
    setDownloadingReportId(reportId);
    setReportsError(null);
    try {
      await api.downloadUsageReport(reportId);
      await loadReports();
    } catch (e) {
      setReportsError((e as Error).message);
    } finally {
      setDownloadingReportId(null);
    }
  }

  async function importReport(reportId: string): Promise<void> {
    setImportingReportId(reportId);
    setReportsError(null);
    try {
      const payload = await api.importUsageReport(reportId);
      onUsageReportImported(payload.import);
      await loadReports();
    } catch (e) {
      setReportsError((e as Error).message);
    } finally {
      setImportingReportId(null);
    }
  }

  useEffect(() => {
    void loadReports();
  }, []);

  useEffect(() => {
    const hasProcessing = reports.some((r) => r.status === "processing");
    if (!hasProcessing) return;
    const handle = window.setInterval(() => {
      void loadReports();
    }, 15000);
    return () => window.clearInterval(handle);
  }, [reports]);

  const accessHint = usageReportAccessHint(reportsError);
  const refreshAllRunning = refreshAllJob?.status === "pending" || refreshAllJob?.status === "running";
  const showRetryRefreshAll =
    refreshAllJob?.status === "failed"
    || refreshAllJob?.status === "completed_with_errors"
    || refreshAllJob?.status === "canceled";

  return (
    <div>
      <div className="panel">
        <h2>Data Operations</h2>
        <div className="ops-actions">
          <button
            onClick={() => {
              void onStartRefreshAll();
            }}
            disabled={refreshAllRunning || refreshing || importing || exporting}
            className={refreshAllRunning ? "btn-busy" : undefined}
          >
            {refreshAllRunning ? "Refresh all in progress…" : "Refresh All Data"}
          </button>
          {refreshAllRunning ? (
            <button
              onClick={() => {
                void onCancelRefreshAll();
              }}
              className="btn-danger"
            >
              Cancel refresh
            </button>
          ) : null}
          {showRetryRefreshAll ? (
            <button
              onClick={() => {
                void onRetryRefreshAll();
              }}
            >
              Retry refresh all
            </button>
          ) : null}
          <button
            onClick={() => {
              void onRefresh();
            }}
            disabled={refreshing || importing || refreshAllRunning}
            className={snapshotDone === true ? "btn-success" : undefined}
          >
            {refreshing ? "Refreshing…" : snapshotDone === true ? "\u2713 Snapshot complete" : "Refresh snapshot"}
          </button>
          <button
            onClick={() => {
              void onExport();
            }}
            disabled={exporting || importing || refreshing}
          >
            {exporting ? "Exporting…" : "Export data"}
          </button>
          <label className={importing || refreshing ? "upload-button upload-disabled" : "upload-button"}>
            {importing ? "Importing…" : "Import file"}
            <input
              type="file"
              accept=".json,.jsonl,.ndjson,.csv,.db,.sqlite,.sqlite3,.gz,application/json,text/csv,application/csv,application/vnd.ms-excel,application/gzip,application/x-sqlite3"
              disabled={importing || refreshing}
              onChange={(event) => {
                void onImport(event.target.files?.[0]);
                event.currentTarget.value = "";
              }}
            />
          </label>
        </div>

        {refreshAllError ? <div className="error">{refreshAllError}</div> : null}
        {refreshAllJob ? (
          <div className="refresh-all-status">
            <div className="refresh-all-summary">
              <strong>Status:</strong> {refreshAllJob.status}
              {refreshAllJob.started_at ? ` | Started: ${refreshAllJob.started_at}` : ""}
              {refreshAllJob.finished_at ? ` | Finished: ${refreshAllJob.finished_at}` : ""}
            </div>
            <table>
              <thead>
                <tr>
                  <th>Data Source</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {refreshAllJob.steps.map((step) => (
                  <tr key={step.key}>
                    <td>{step.label}</td>
                    <td><span className={`step-badge step-${step.status}`}>{step.status}</span></td>
                    <td>{step.message}</td>
                    <td>{step.updated_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {refreshAllJob.errors.length ? (
              <div className="warning-note">{refreshAllJob.errors.join(" | ")}</div>
            ) : null}
          </div>
        ) : null}
      </div>

      {refreshing ? <div className="snapshot-progress"><div className="snapshot-progress-bar" /></div> : null}
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

      <div className="panel">
        <h2>Last Data Load</h2>
        <table>
          <thead>
            <tr>
              <th>Data Type</th>
              <th>Last Loaded</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>API</td>
              <td>{apiLabel}</td>
              <td>GitHub API snapshot</td>
            </tr>
            <tr>
              <td>CSV</td>
              <td>{csvLabel}</td>
              <td>{csvSource ?? "n/a"}</td>
            </tr>
            <tr>
              <td>JSON</td>
              <td>{jsonLabel}</td>
              <td>{jsonSource ?? "n/a"}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2>Enterprise Usage Reports</h2>
        <div className="ops-grid">
          <label>
            Report type
            <select value={reportType} onChange={(e) => setReportType(e.target.value as UsageReportType)}>
              <option value="ai_credit">ai_credit</option>
              <option value="premium_request">premium_request</option>
              <option value="detailed">detailed</option>
              <option value="summarized">summarized</option>
            </select>
          </label>
          <label>
            Start date
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label>
            End date
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </label>
          <label className="checkbox-inline">
            <input
              type="checkbox"
              checked={sendEmail}
              onChange={(e) => setSendEmail(e.target.checked)}
            />
            Send email when ready
          </label>
        </div>

        <div className="ops-actions">
          <button
            onClick={() => {
              void createReport();
            }}
            disabled={creatingReport || reportsLoading}
          >
            {creatingReport ? "Creating…" : "Create usage report"}
          </button>
          <button
            onClick={() => {
              void loadReports();
            }}
            disabled={reportsLoading || creatingReport}
          >
            {reportsLoading ? "Refreshing…" : "Refresh report list"}
          </button>
        </div>

        {reportsError ? <div className="error">{reportsError}</div> : null}
        {accessHint ? <div className="warning-note">{accessHint}</div> : null}

        {reports.length === 0 ? (
          <p className="muted">No usage-report exports found.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Created</th>
                <th>Type</th>
                <th>Range</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.id}>
                  <td>{r.created_at ?? "n/a"}</td>
                  <td>{r.report_type}</td>
                  <td>{r.start_date} to {r.end_date}</td>
                  <td>{r.status}</td>
                  <td>
                    <button
                      onClick={() => {
                        void downloadReport(r.id);
                      }}
                      disabled={r.status !== "completed" || downloadingReportId === r.id}
                    >
                      {downloadingReportId === r.id ? "Downloading…" : "Download"}
                    </button>
                    <button
                      onClick={() => {
                        void importReport(r.id);
                      }}
                      disabled={r.status !== "completed" || importingReportId === r.id}
                    >
                      {importingReportId === r.id ? "Importing…" : "Import"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
