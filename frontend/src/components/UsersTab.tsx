import { useEffect, useState } from "react";
import { api, type UserDetail, type UserRow } from "../api";
import { defaultWindow, DateRangeSelector, toWindowParams, type WindowState } from "./DateRangeSelector";
import { fmtMoney, fmtNum, Kpi } from "./TeamsTab";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

type StatusFilter = "all" | "active" | "stale" | "never_used";
type SortCol = "login" | "status" | "prs" | "net_lines" | "ai_credits";
type SortDir = "asc" | "desc";

export function UsersTab(): JSX.Element {
  const [win, setWin] = useState<WindowState>(defaultWindow(30));
  const [users, setUsers] = useState<UserRow[]>([]);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const initialUser = new URLSearchParams(window.location.hash.split("?")[1] || "").get("user");
  const [selected, setSelected] = useState<string | null>(initialUser);
  const [detail, setDetail] = useState<UserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortCol, setSortCol] = useState<SortCol>("prs");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  useEffect(() => {
    api
      .users(toWindowParams(win))
      .then((rows) => {
        setUsers(rows);
        if (!selected && rows.length) setSelected(rows[0].login);
      })
      .catch((e: Error) => setError(e.message));
  }, [win.start, win.end]);

  useEffect(() => {
    if (!selected) return;
    setDetail(null);
    api
      .userDetail(selected, toWindowParams(win))
      .then(setDetail)
      .catch((e: Error) => setError(e.message));
  }, [selected, win.start, win.end]);

  const filtered = users.filter((u) => {
    if (filter !== "all" && u.status !== filter) return false;
    if (query && !u.login.toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  });

  const sorted = [...filtered].sort((a, b) => {
    const va = a[sortCol];
    const vb = b[sortCol];
    let cmp: number;
    if (typeof va === "string" && typeof vb === "string") {
      cmp = va.localeCompare(vb);
    } else {
      cmp = (va as number) - (vb as number);
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  function toggleSort(col: SortCol): void {
    if (sortCol === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(col);
      setSortDir("desc");
    }
  }

  function sortIndicator(col: SortCol): string {
    if (sortCol !== col) return "";
    return sortDir === "asc" ? " ▲" : " ▼";
  }

  return (
    <div>
      <DateRangeSelector value={win} onChange={setWin} />
      <div className="panel">
        <div className="muted" style={{ marginBottom: 8 }}>
          <strong>Note:</strong> GitHub does not expose per-user Copilot acceptance/model/language metrics.
          The list below shows seat lifecycle + PR activity per user as the best available per-user signal.
        </div>
        <div className="filter-bar">
          <input
            type="search"
            placeholder="Filter login…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {(["all", "active", "stale", "never_used"] as StatusFilter[]).map((f) => (
            <button
              key={f}
              className={filter === f ? "chip chip-on" : "chip"}
              onClick={() => setFilter(f)}
            >
              {f.replace("_", " ")}
            </button>
          ))}
          <span className="muted" style={{ marginLeft: "auto" }}>
            {filtered.length} of {users.length} users
          </span>
        </div>
      </div>

      {error ? <div className="error">{error}</div> : null}

      <div className="split">
        <div className="panel" style={{ minWidth: 340 }}>
          <table>
            <thead>
              <tr>
                <th className="sortable-th" onClick={() => toggleSort("login")}>User{sortIndicator("login")}</th>
                <th className="sortable-th" onClick={() => toggleSort("status")}>Status{sortIndicator("status")}</th>
                <th className="sortable-th" onClick={() => toggleSort("prs")}>PRs{sortIndicator("prs")}</th>
                <th className="sortable-th" onClick={() => toggleSort("net_lines")}>Net Lines{sortIndicator("net_lines")}</th>
                <th className="sortable-th" onClick={() => toggleSort("ai_credits")}>AI Credits{sortIndicator("ai_credits")}</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((u) => (
                <tr
                  key={u.login}
                  className={u.login === selected ? "row-selected" : undefined}
                  onClick={() => setSelected(u.login)}
                  style={{ cursor: "pointer" }}
                >
                  <td>
                    {u.login}
                    <div className="muted">{u.team ?? "—"}</div>
                  </td>
                  <td>
                    <span className={`badge badge-${u.status}`}>{u.status.replace("_", " ")}</span>
                  </td>
                  <td>{u.prs}</td>
                  <td>{u.net_lines.toLocaleString()}</td>
                  <td>{fmtNum(u.ai_credits)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ flex: 1 }}>
          {detail ? <UserDetailView detail={detail} /> : <div className="loading">Loading…</div>}
        </div>
      </div>
    </div>
  );
}

function UserDetailView({ detail }: { detail: UserDetail }): JSX.Element {
  return (
    <>
      <div className="panel">
        <h2>
          {detail.login} — {detail.window_start} → {detail.window_end}
        </h2>
        <div className="kpi-grid">
          <Kpi
            label="Seat"
            value={detail.has_seat ? "yes" : "no"}
            sub={detail.teams.join(", ") || "no team"}
            tooltip={
              "Whether this user currently holds a Copilot seat (joined on the seats snapshot). " +
              "Sub-value lists GitHub teams they belong to."
            }
          />
          <Kpi
            label="Window cost"
            value={fmtMoney(detail.totals.window_cost_usd)}
            sub="actual consumption"
            tooltip={
              "Actual Copilot consumption charges attributed to this user across the window " +
              "(sum of billing net_amount_usd). GitHub bills Copilot per usage, not per seat; " +
              "zero if no consumption was attributed to this login."
            }
          />
          <Kpi
            label="PRs (window)"
            value={detail.totals.prs.toLocaleString()}
            sub={`${detail.totals.merged} merged`}
            tooltip={
              "Count of pull requests authored by this user where created_at falls in the window. " +
              "Sub-count is the subset that were merged."
            }
          />
          <Kpi
            label="Net lines"
            value={detail.totals.net_lines.toLocaleString()}
            sub={`+${detail.totals.additions.toLocaleString()} / -${detail.totals.deletions.toLocaleString()}`}
            tooltip={
              "Sum of (additions − deletions) across the user's PRs in the window. " +
              "Code volume signal — not a quality measure."
            }
          />
          <Kpi
            label="Avg cycle time"
            value={detail.totals.avg_cycle_time_hours === null ? "—" : `${detail.totals.avg_cycle_time_hours} h`}
            tooltip={
              "Mean hours from PR created_at to merged_at across this user's MERGED PRs in the window. " +
              "Lower = faster delivery."
            }
          />
          <Kpi
            label="Last activity"
            value={detail.seat?.last_activity_at ? String(detail.seat.last_activity_at).slice(0, 10) : "—"}
            sub={(detail.seat?.last_activity_editor as string) ?? ""}
            tooltip={
              "Most recent Copilot telemetry timestamp from the seat record " +
              "(/copilot/billing/seats). Sub-value is the editor reported by GitHub."
            }
          />
          <Kpi
            label="AI credits"
            value={fmtNum(detail.totals.ai_credits)}
            sub={fmtMoney(detail.totals.ai_credit_cost_usd)}
            tooltip={
              "Sum of AI-credit quantity attributed to this user in the window " +
              "(enhanced-billing API). Sub-value is sum of net_amount_usd."
            }
          />
        </div>
      </div>

      <div className="panel">
        <h2>AI Credit Usage (Billing-Derived)</h2>
        <div className="muted" style={{ marginBottom: 8 }}>
          <strong>Tokens:</strong> {detail.ai_credits.tokens_note}
        </div>
        <div className="row-grid">
          <div>
            <h3 className="subhead">By SKU</h3>
            <table>
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Quantity</th>
                  <th>Cost</th>
                </tr>
              </thead>
              <tbody>
                {detail.ai_credits.by_sku.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="muted">
                      No billing-usage rows for this user — enhanced billing API may be unavailable.
                    </td>
                  </tr>
                ) : (
                  detail.ai_credits.by_sku.map((s) => (
                    <tr key={s.sku}>
                      <td>{s.sku}</td>
                      <td>{fmtNum(s.quantity)}</td>
                      <td>{fmtMoney(s.net_amount_usd)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div>
            <h3 className="subhead">Daily AI Credits</h3>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>AI Credits</th>
                </tr>
              </thead>
              <tbody>
                {detail.ai_credits.daily_ai_credits.length === 0 ? (
                  <tr>
                    <td colSpan={2} className="muted">
                      No daily AI-credit rows in window.
                    </td>
                  </tr>
                ) : (
                  detail.ai_credits.daily_ai_credits.map((d) => (
                    <tr key={d.date}>
                      <td>{d.date}</td>
                      <td>{fmtNum(d.ai_credits)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <ModelUsagePanel detail={detail} />

      <div className="panel">
        <h2>Recent PRs</h2>
        <table>
          <thead>
            <tr>
              <th>Repo / PR</th>
              <th>Title</th>
              <th>State</th>
              <th>+lines</th>
              <th>-lines</th>
              <th>Files</th>
              <th>Created</th>
              <th>Merged</th>
            </tr>
          </thead>
          <tbody>
            {detail.recent_prs.length === 0 ? (
              <tr>
                <td colSpan={8} className="muted">
                  No PRs in this window.
                </td>
              </tr>
            ) : (
              detail.recent_prs.map((p) => (
                <tr key={`${p.repo}-${p.number}`}>
                  <td>
                    {p.repo}#{p.number}
                  </td>
                  <td title={p.title} style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {p.title}
                  </td>
                  <td>{p.state}</td>
                  <td>{fmtNum(p.additions)}</td>
                  <td>{fmtNum(p.deletions)}</td>
                  <td>{fmtNum(p.changed_files)}</td>
                  <td>{p.created_at?.slice(0, 10) ?? "—"}</td>
                  <td>{p.merged_at?.slice(0, 10) ?? "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2>Daily PR Activity</h2>
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>PRs</th>
              <th>Merged</th>
              <th>+lines</th>
              <th>-lines</th>
            </tr>
          </thead>
          <tbody>
            {detail.daily.length === 0 ? (
              <tr>
                <td colSpan={5} className="muted">
                  No activity recorded.
                </td>
              </tr>
            ) : (
              detail.daily.map((d) => (
                <tr key={d.date}>
                  <td>{d.date}</td>
                  <td>{d.prs}</td>
                  <td>{d.merged}</td>
                  <td>{fmtNum(d.additions)}</td>
                  <td>{fmtNum(d.deletions)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ModelUsagePanel({ detail }: { detail: UserDetail }): JSX.Element {
  const byModel = detail.ai_credits.by_model;
  const total = detail.ai_credits.ai_credits;
  const totalCost = detail.ai_credits.ai_credit_cost_usd;
  const distinctModels = byModel.length;
  const topModel = byModel[0];
  const topModelShare = topModel ? topModel.share : 0;
  const concentrationLabel =
    topModelShare >= 0.8
      ? "single-model"
      : topModelShare >= 0.5
      ? "dominant model"
      : "diversified";

  return (
    <div className="panel">
      <h2>Model Usage (AI Credits)</h2>
      <div className="muted" style={{ marginBottom: 8 }}>
        Per-user model breakdown is only available for billed AI credits
        (chat / agent / Copilot Coding Agent). GitHub does not expose per-user
        model breakdowns for inline completion suggestions — those numbers exist
        only at org/team scope (see the Quality tab).
      </div>
      <div className="kpi-grid">
        <Kpi
          label="Total AI credits"
          value={fmtNum(total)}
          sub={fmtMoney(totalCost)}
          tooltip={
            "Sum of AI-credit quantity attributed to this user in the window " +
            "(enhanced-billing API). Sub-value is the matching net_amount_usd."
          }
        />
        <Kpi
          label="Distinct models"
          value={distinctModels.toString()}
          sub={`across ${detail.ai_credits.by_sku.length} SKUs`}
          tooltip={
            "How many distinct models this user has billed AI credits against. " +
            "Higher = more experimentation; lower = standardized on a single model."
          }
        />
        <Kpi
          label="Top model"
          value={topModel ? topModel.model : "—"}
          sub={topModel ? `${(topModelShare * 100).toFixed(0)}% share · ${concentrationLabel}` : ""}
          tooltip={
            "Model with the highest AI-credit count for this user in the window. " +
            "Share = top_model_credits / total_ai_credits. " +
            "≥80% = single-model user; ≥50% = dominant model; otherwise diversified."
          }
        />
      </div>

      <UserModelBarChart byModel={byModel} />

      <h3 className="subhead" style={{ marginTop: 16 }}>By Model</h3>
      <table>
        <thead>
          <tr>
            <th>Model</th>
            <th>AI Credits</th>
            <th>Share</th>
            <th>Cost</th>
          </tr>
        </thead>
        <tbody>
          {byModel.length === 0 ? (
            <tr>
              <td colSpan={4} className="muted">
                No AI-credit rows in window — nothing to break down.
              </td>
            </tr>
          ) : (
            byModel.map((m) => (
              <tr key={m.model}>
                <td>{m.model}</td>
                <td>{fmtNum(m.ai_credits)}</td>
                <td>
                  <ModelShareBar share={m.share} />
                </td>
                <td>{fmtMoney(m.net_amount_usd)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function ModelShareBar({ share }: { share: number }): JSX.Element {
  const pct = Math.max(0, Math.min(1, share)) * 100;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        minWidth: 140,
      }}
    >
      <div
        style={{
          flex: 1,
          height: 6,
          background: "var(--border)",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: "var(--accent, #58a6ff)",
          }}
        />
      </div>
      <span style={{ fontVariantNumeric: "tabular-nums", minWidth: 44, textAlign: "right" }}>
        {pct.toFixed(1)}%
      </span>
    </div>
  );
}

function UserModelBarChart({
  byModel,
}: {
  byModel: { model: string; ai_credits: number; net_amount_usd: number; share: number }[];
}): JSX.Element {
  const data = byModel.slice(0, 10);

  if (data.length === 0) {
    return <div className="muted" style={{ marginTop: 12 }}>No model data for this user in the selected window.</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={280} style={{ marginTop: 12 }}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
        <XAxis dataKey="model" stroke="#8b949e" fontSize={11} angle={-35} textAnchor="end" height={70} interval={0} tickLine={false} />
        <YAxis stroke="#8b949e" fontSize={11} label={{ value: "AI credits", angle: -90, position: "insideLeft", style: { fill: "#8b949e", fontSize: 11 } }} />
        <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #30363d" }} />
        <Bar dataKey="ai_credits" fill="#bc8cff" name="AI credits" />
      </BarChart>
    </ResponsiveContainer>
  );
}
