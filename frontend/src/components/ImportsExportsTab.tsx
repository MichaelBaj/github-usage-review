import type { DbImportResult, ImportResult } from "../api";

export interface DataLoadEntry {
  name: string;
  dataType: string;
  lastLoaded: string;
  source: string;
}

interface ImportsExportsTabProps {
  dataLoadEntries: DataLoadEntry[];
  refreshing: boolean;
  importing: boolean;
  exporting: boolean;
  snapshotDone: boolean | null;
  error: string | null;
  importResult: ImportResult | null;
  dbImportResult: DbImportResult | null;
  onRefresh: () => Promise<void>;
  onExport: () => Promise<void>;
  onImport: (file: File | undefined, sourceHint?: string) => Promise<void>;
}

export function ImportsExportsTab({
  dataLoadEntries,
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
}: ImportsExportsTabProps): JSX.Element {
  return (
    <div>
      <div className="panel">
        <h2>Data Operations</h2>
        <div className="ops-actions">
          <button
            onClick={() => {
              void onRefresh();
            }}
            disabled={refreshing || importing}
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
              <th>Data Source</th>
              <th>Data Type</th>
              <th>Last Loaded</th>
              <th>Source</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {dataLoadEntries.map((entry) => (
              <tr key={entry.name}>
                <td>{entry.name}</td>
                <td>{entry.dataType}</td>
                <td>{entry.lastLoaded}</td>
                <td>{entry.source}</td>
                <td>
                  {entry.dataType === "NDJSON" ? (
                    <label className={importing ? "upload-button upload-disabled" : "upload-button"}>
                      Import
                      <input
                        type="file"
                        accept=".json,.jsonl,.ndjson"
                        disabled={importing}
                        onChange={(event) => {
                          void onImport(event.target.files?.[0], entry.source);
                          event.currentTarget.value = "";
                        }}
                      />
                    </label>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
