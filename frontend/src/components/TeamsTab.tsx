import { useEffect, useRef, useState } from "react";
import { api, type ModelBreakdown, type TeamDetail, type TeamRow } from "../api";
import { defaultWindow, DateRangeSelector, toWindowParams, type WindowState } from "./DateRangeSelector";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

type TeamSortCol = "team" | "members_total" | "active_members" | "ai_credits";
type SortDir = "asc" | "desc";

/** Renders the per-team tab: team list on the left, detail on the right. */
export function TeamsTab(): JSX.Element {
  const [win, setWin] = useState<WindowState>(defaultWindow(30));
  const [teams, setTeams] = useState<TeamRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<TeamDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortCol, setSortCol] = useState<TeamSortCol>("active_members");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  useEffect(() => {
    api
      .teams(toWindowParams(win))
      .then((rows) => {
        setTeams(rows);
        if (!selected && rows.length) setSelected(rows[0].team);
      })
      .catch((e: Error) => setError(e.message));
  }, [win.start, win.end]);

  const sorted = [...teams].sort((a, b) => {
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

  function toggleSort(col: TeamSortCol): void {
    if (sortCol === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(col);
      setSortDir("desc");
    }
  }

  function sortIndicator(col: TeamSortCol): string {
    if (sortCol !== col) return "";
    return sortDir === "asc" ? " ▲" : " ▼";
  }

  useEffect(() => {
    if (!selected) return;
    setDetail(null);
    api
      .teamDetail(selected, toWindowParams(win))
      .then(setDetail)
      .catch((e: Error) => setError(e.message));
  }, [selected, win.start, win.end]);

  return (
    <div>
      <DateRangeSelector value={win} onChange={setWin} />
      {error ? <div className="error">{error}</div> : null}
      <div className="split">
        <div className="panel" style={{ minWidth: 320 }}>
          <h2>Teams</h2>
          <div className="muted" style={{ marginBottom: 8 }}>
            Derived from per-user data (seat activity + billing) rolled up by team membership.
          </div>
          <table>
            <thead>
              <tr>
                <th className="sortable-th" onClick={() => toggleSort("team")}>Team{sortIndicator("team")}</th>
                <th className="sortable-th" onClick={() => toggleSort("members_total")}>Members{sortIndicator("members_total")}</th>
                <th className="sortable-th" onClick={() => toggleSort("active_members")}>Active{sortIndicator("active_members")}</th>
                <th className="sortable-th" onClick={() => toggleSort("ai_credits")}>Premium Reqs{sortIndicator("ai_credits")}</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((t) => (
                <tr
                  key={t.team}
                  className={t.team === selected ? "row-selected" : undefined}
                  onClick={() => setSelected(t.team)}
                  style={{ cursor: "pointer" }}
                >
                  <td>{t.team}</td>
                  <td>{t.members_total}</td>
                  <td>
                    {t.active_members}
                    {t.members_with_seats ? ` (${(t.adoption_rate * 100).toFixed(0)}%)` : ""}
                  </td>
                  <td>{fmtNum(t.ai_credits)}</td>
                </tr>
              ))}
              {sorted.length === 0 ? (
                <tr>
                  <td colSpan={4} className="muted">
                    No teams synced. Check that the PAT has read:org.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div style={{ flex: 1 }}>{detail ? <TeamDetailView detail={detail} /> : <div className="loading">Loading…</div>}</div>
      </div>
    </div>
  );
}

function TeamDetailView({ detail }: { detail: TeamDetail }): JSX.Element {
  return (
    <>
      <div className="panel">
        <h2>
          {detail.team} — {detail.window_start} → {detail.window_end}
        </h2>
        <div className="muted" style={{ marginBottom: 8 }}>
          Built from per-user data (seat activity, billing, PRs) aggregated over team membership.
          GitHub does not expose team-scoped Copilot metrics for this org.
        </div>
        <div className="kpi-grid">
          <Kpi
            label="Members"
            value={String(detail.members_total)}
            sub={`${detail.members_with_seats} with Copilot`}
            tooltip={
              "Count of GitHub team members from /orgs/{org}/teams/{slug}/members. " +
              "Sub-count is members that currently hold a Copilot seat."
            }
          />
          <Kpi
            label="Active members"
            value={String(detail.activity.active_members)}
            sub={`${detail.activity.stale_members} stale · ${detail.activity.never_used_members} never used`}
            tooltip={
              "Members whose Copilot seat shows activity within the staleness window " +
              "(seats.last_activity_at). Derived per-user, then counted by team membership."
            }
          />
          <Kpi
            label="Adoption rate"
            value={fmtPct(detail.activity.adoption_rate)}
            sub={`${detail.activity.active_members} / ${detail.members_with_seats} seats`}
            tooltip={
              "Active members ÷ members holding a Copilot seat. Per-user seat activity " +
              "rolled up to the team."
            }
          />
          <Kpi
            label="Window cost"
            value={fmtMoney(detail.window_cost_usd)}
            sub={`${fmtMoney(detail.monthly_cost_usd)}/mo`}
            tooltip={
              "Actual Copilot consumption charges attributed to this team's members " +
              "over the window (sum of billing net_amount_usd). Monthly run-rate " +
              "extrapolates that to 30 days. GitHub bills Copilot per usage, not per seat."
            }
          />
          <Kpi
            label="AI credits"
            value={fmtNum(detail.ai_credits.ai_credits)}
            sub={`${fmtMoney(detail.ai_credits.ai_credit_cost_usd)} billed`}
            tooltip={
              "Sum of AI-credit quantity across this team's members in the window " +
              "(enhanced-billing API, joined on team_members.login)."
            }
          />
          <Kpi
            label="Pull requests"
            value={fmtNum(detail.activity.prs)}
            sub={`${detail.activity.merged_prs} merged`}
            tooltip={
              "PRs authored by team members in the window (pull_requests joined on author). " +
              "Best available per-user productivity signal without team Copilot metrics."
            }
          />
          <Kpi
            label="Net lines"
            value={fmtNum(detail.activity.net_lines)}
            tooltip="Additions − deletions across team members' PRs in the window."
          />
        </div>
      </div>

      <div className="panel">
        <h2>Models</h2>
        <TeamModelBarChart models={detail.models} />
      </div>

      <div className="panel">
        <h2>Member Activity</h2>
        <table>
          <thead>
            <tr>
              <th>Member</th>
              <th>Status</th>
              <th>Last Active</th>
              <th>PRs</th>
              <th>AI Credits</th>
              <th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {detail.member_activity.map((m) => (
              <tr key={m.login}>
                <td>{m.login}</td>
                <td>
                  <span className={`badge badge-${m.status}`}>{m.status.replace("_", " ")}</span>
                </td>
                <td>{m.last_activity_at ? m.last_activity_at.slice(0, 10) : "—"}</td>
                <td>{fmtNum(m.prs)}</td>
                <td>{fmtNum(m.ai_credits)}</td>
                <td>{fmtMoney(m.cost_usd)}</td>
              </tr>
            ))}
            {detail.member_activity.length === 0 ? (
              <tr>
                <td colSpan={6} className="muted">
                  No members synced for this team. Check that the PAT has read:org.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2>PR Activity</h2>
        <PrCorrelationTable c={detail.pr_correlation} />
      </div>

      <div className="panel">
        <h2>AI Credit Usage (Billing-Derived)</h2>
        <AiCreditsTeamBlock data={detail.ai_credits} />
      </div>

      <div className="panel">
        <h2>Members ({detail.members.length})</h2>
        <div className="member-list">
          {detail.members.length
            ? detail.members.map((m) => (
                <a
                  key={m}
                  className="chip"
                  href={`#users?user=${encodeURIComponent(m)}`}
                >
                  {m}
                </a>
              ))
            : <span className="muted">No team members synced. Check that the GitHub PAT has read:org.</span>}
        </div>
      </div>
    </>
  );
}

export function ModelTable({ data }: { data: ModelBreakdown }): JSX.Element {
  return (
    <>
      <h3 className="subhead">Code Models</h3>
      <table>
        <thead>
          <tr>
            <th>Editor</th>
            <th>Model</th>
            <th>Suggestions</th>
            <th>Acceptances</th>
            <th>Acc Rate</th>
            <th>Lines Acc</th>
            <th>AI Credits</th>
          </tr>
        </thead>
        <tbody>
          {data.code.map((r) => (
            <tr key={`${r.editor}|${r.model}`}>
              <td>{r.editor}</td>
              <td>{r.model}</td>
              <td>{r.suggestions.toLocaleString()}</td>
              <td>{r.acceptances.toLocaleString()}</td>
              <td>{fmtPct(r.acceptance_rate)}</td>
              <td>{r.lines_accepted.toLocaleString()}</td>
              <td>{r.ai_credits.toLocaleString()}</td>
            </tr>
          ))}
          {data.code.length === 0 ? (
            <tr>
              <td colSpan={7} className="muted">
                No code-model data for window.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
      <h3 className="subhead" style={{ marginTop: 16 }}>
        Chat Models
      </h3>
      <table>
        <thead>
          <tr>
            <th>Editor</th>
            <th>Model</th>
            <th>Chats</th>
            <th>Insertions</th>
            <th>Copies</th>
            <th>AI Credits</th>
          </tr>
        </thead>
        <tbody>
          {data.chat.map((r) => (
            <tr key={`${r.editor}|${r.model}`}>
              <td>{r.editor}</td>
              <td>{r.model}</td>
              <td>{r.chats.toLocaleString()}</td>
              <td>{r.chat_insertions.toLocaleString()}</td>
              <td>{r.chat_copies.toLocaleString()}</td>
              <td>{r.ai_credits.toLocaleString()}</td>
            </tr>
          ))}
          {data.chat.length === 0 ? (
            <tr>
              <td colSpan={6} className="muted">
                No chat-model data for window.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </>
  );
}

export function PrCorrelationTable({ c }: { c: import("../api").PrCorrelation }): JSX.Element {
  const total = {
    pr_count: c.ai_authored.pr_count + c.non_ai_authored.pr_count,
    merged_count: c.ai_authored.merged_count + c.non_ai_authored.merged_count,
    merge_rate: c.total_prs ? (c.ai_authored.merged_count + c.non_ai_authored.merged_count) / c.total_prs : 0,
    avg_cycle_time_hours: c.ai_authored.avg_cycle_time_hours,
    avg_pr_size_lines: c.ai_authored.avg_pr_size_lines,
    avg_review_comments_per_pr: c.ai_authored.avg_review_comments_per_pr,
    additions: c.ai_authored.additions + c.non_ai_authored.additions,
    deletions: c.ai_authored.deletions + c.non_ai_authored.deletions,
    net_lines: c.ai_authored.net_lines + c.non_ai_authored.net_lines,
  };
  const rows: { label: string; value: string }[] = [
    { label: "PRs", value: total.pr_count.toLocaleString() },
    { label: "Merged", value: total.merged_count.toLocaleString() },
    { label: "Merge rate", value: fmtPct(total.merge_rate) },
    { label: "Avg cycle time (h)", value: fmtNum(total.avg_cycle_time_hours) },
    { label: "Avg PR size (lines)", value: fmtNum(total.avg_pr_size_lines) },
    { label: "Avg review comments / PR", value: fmtNum(total.avg_review_comments_per_pr) },
    { label: "Total additions", value: total.additions.toLocaleString() },
    { label: "Total deletions", value: total.deletions.toLocaleString() },
    { label: "Net lines", value: total.net_lines.toLocaleString() },
  ];
  return (
    <table>
      <thead>
        <tr>
          <th>Metric</th>
          <th>Value</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label}>
            <td>{r.label}</td>
            <td>{r.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Kpi({
  label,
  value,
  sub,
  tooltip,
}: {
  label: string;
  value: string;
  sub?: string;
  tooltip?: string;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent): void {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onEsc(e: KeyboardEvent): void {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  if (!tooltip) {
    return (
      <div className="kpi">
        <div className="label">{label}</div>
        <div className="value">{value}</div>
        {sub ? <div className="sub">{sub}</div> : null}
      </div>
    );
  }

  return (
    <div
      ref={ref}
      className={`kpi kpi-tip${open ? " kpi-tip-open" : ""}`}
      tabIndex={0}
      role="button"
      aria-label={`${label}. ${tooltip}`}
      aria-expanded={open}
      onClick={() => setOpen((v) => !v)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setOpen((v) => !v);
        }
      }}
    >
      <div className="label">
        {label}
        <span className="kpi-info" aria-hidden="true">ⓘ</span>
      </div>
      <div className="value">{value}</div>
      {sub ? <div className="sub">{sub}</div> : null}
      <div className="kpi-tooltip" role="tooltip">
        {tooltip}
      </div>
    </div>
  );
}

export function fmtMoney(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function fmtPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

export function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString();
}

export function AiCreditsTeamBlock({
  data,
}: {
  data: import("../api").AiCreditsTeam;
}): JSX.Element {
  return (
    <>
      <div className="muted" style={{ marginBottom: 8 }}>
        <strong>Tokens:</strong> {data.tokens_note}
      </div>
      <div className="kpi-grid">
        <Kpi label="AI credits (window)" value={fmtNum(data.ai_credits)} />
        <Kpi label="Cost (window)" value={fmtMoney(data.ai_credit_cost_usd)} />
        <Kpi label="Members measured" value={String(data.members)} />
      </div>
      <h3 className="subhead" style={{ marginTop: 16 }}>
        Top Users in This Team
      </h3>
      <table>
        <thead>
          <tr>
            <th>User</th>
            <th>AI Credits</th>
            <th>Cost</th>
          </tr>
        </thead>
        <tbody>
          {data.top_users.length === 0 ? (
            <tr>
              <td colSpan={3} className="muted">
                No billing-usage data — enhanced billing API may be unavailable on this org tier.
              </td>
            </tr>
          ) : (
            data.top_users.map((u) => (
              <tr key={u.login}>
                <td>{u.login}</td>
                <td>{fmtNum(u.ai_credits)}</td>
                <td>{fmtMoney(u.net_amount_usd)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </>
  );
}

function TeamModelBarChart({ models }: { models: ModelBreakdown }): JSX.Element {
  const modelMap = new Map<string, { model: string; requests: number; ai_credits: number }>();
  for (const r of [...models.code, ...models.chat]) {
    const entry = modelMap.get(r.model) || { model: r.model, requests: 0, ai_credits: 0 };
    entry.requests += r.suggestions + r.chats;
    entry.ai_credits += r.ai_credits || 0;
    modelMap.set(r.model, entry);
  }

  const hasMetrics = [...modelMap.values()].some((d) => d.requests > 0);
  const data = [...modelMap.values()]
    .sort((a, b) =>
      hasMetrics ? b.requests - a.requests : b.ai_credits - a.ai_credits
    )
    .slice(0, 10);

  if (data.length === 0) {
    return <div className="muted">No model data for this team in the selected window.</div>;
  }

  if (hasMetrics) {
    return (
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
          <XAxis dataKey="model" stroke="#8b949e" fontSize={11} angle={-35} textAnchor="end" height={70} interval={0} tickLine={false} />
          <YAxis stroke="#8b949e" fontSize={11} label={{ value: "Requests", angle: -90, position: "insideLeft", style: { fill: "#8b949e", fontSize: 11 } }} />
          <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #30363d" }} />
          <Bar dataKey="requests" fill="#bc8cff" name="Requests" />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={320}>
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
