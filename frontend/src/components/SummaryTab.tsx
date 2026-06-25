import { useEffect, useState } from "react";
import {
  api,
  type AiCreditBalancedUser,
  type AiCreditTopUsersPerModel,
  type Breakdowns,
  type CostWindow,
  type Kpis,
  type AiCreditsSummary,
  type ModelBreakdown,
  type StaleSeat,
  type TeamRow,
} from "../api";
import { KpiCards } from "./KpiCards";
import { TeamLeaderboard } from "./TeamLeaderboard";
import { StaleSeats } from "./StaleSeats";
import { BreakdownCharts } from "./BreakdownCharts";
import {
  defaultWindow,
  DateRangeSelector,
  toWindowParams,
  type WindowState,
} from "./DateRangeSelector";
import { fmtMoney, fmtNum, Kpi } from "./TeamsTab";

interface State {
  loading: boolean;
  error: string | null;
  kpis: Kpis | null;
  teams: TeamRow[];
  stale: StaleSeat[];
  breakdowns: Breakdowns | null;
  cost: CostWindow | null;
  premium: AiCreditsSummary | null;
  modelCreditsTotal: number | null;
}

const initial: State = {
  loading: true,
  error: null,
  kpis: null,
  teams: [],
  stale: [],
  breakdowns: null,
  cost: null,
  premium: null,
  modelCreditsTotal: null,
};

function modelCreditsGrandTotal(data: ModelBreakdown): number {
  const byModel = new Map<string, number>();
  for (const row of [...data.code, ...data.chat]) {
    const modelKey = (row.model || "unknown").toLowerCase();
    byModel.set(modelKey, Math.max(byModel.get(modelKey) ?? 0, row.ai_credits || 0));
  }
  return Array.from(byModel.values()).reduce((sum, value) => sum + value, 0);
}

function TopUsersPerModelTable({ models }: { models: AiCreditTopUsersPerModel[] }): JSX.Element {
  if (models.length === 0) {
    return <p className="muted">No per-model user AI-credit data available for this window.</p>;
  }

  const rows = models.flatMap((model) =>
    model.top_users.map((u, idx) => ({
      model: model.model,
      total: model.total_ai_credits,
      login: u.login,
      ai_credits: u.ai_credits,
      percentage: u.percentage,
      showModel: idx === 0,
      rowSpan: model.top_users.length,
    }))
  );

  return (
    <table>
      <thead>
        <tr>
          <th>Model</th>
          <th>Total</th>
          <th>Username</th>
          <th>Quantity</th>
          <th>Percentage</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={`${r.model}:${r.login}`}>
            {r.showModel ? <td rowSpan={r.rowSpan}>{r.model}</td> : null}
            {r.showModel ? <td rowSpan={r.rowSpan}>{fmtNum(r.total)}</td> : null}
            <td>{r.login}</td>
            <td>{fmtNum(r.ai_credits)}</td>
            <td>{r.percentage.toFixed(2)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BalancedUsersTable({ users }: { users: AiCreditBalancedUser[] }): JSX.Element {
  if (users.length === 0) {
    return <p className="muted">No balanced users found for this window.</p>;
  }

  const rows = users.flatMap((user) =>
    user.models.map((m, idx) => ({
      login: user.login,
      total: user.total_ai_credits,
      highPct: user.high_pct,
      lowPct: user.low_pct,
      model: m.model,
      quantity: m.quantity,
      pct: m.pct,
      tier: m.tier,
      showUser: idx === 0,
      rowSpan: user.models.length,
    }))
  );

  return (
    <table>
      <thead>
        <tr>
          <th>User</th>
          <th className="num-col">Total</th>
          <th className="num-col">High %</th>
          <th className="num-col">Low %</th>
          <th>Model</th>
          <th className="num-col">Quantity</th>
          <th className="num-col">Percentage</th>
          <th>Tier</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={`${r.login}:${r.model}`}>
            {r.showUser ? <td rowSpan={r.rowSpan}>{r.login}</td> : null}
            {r.showUser ? <td className="num-col" rowSpan={r.rowSpan}>{fmtNum(r.total)}</td> : null}
            {r.showUser ? <td className="num-col" rowSpan={r.rowSpan}>{r.highPct.toFixed(0)}%</td> : null}
            {r.showUser ? <td className="num-col" rowSpan={r.rowSpan}>{r.lowPct.toFixed(0)}%</td> : null}
            <td>{r.model}</td>
            <td className="num-col">{fmtNum(r.quantity)}</td>
            <td className="num-col">{r.pct.toFixed(2)}%</td>
            <td>{r.tier}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function SummaryTab(): JSX.Element {
  const [win, setWin] = useState<WindowState>(defaultWindow(30));
  const [state, setState] = useState<State>(initial);

  async function load(): Promise<void> {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const params = toWindowParams(win);
      const [kpis, teams, stale, breakdowns, cost, premium, models] = await Promise.all([
        api.kpis(params),
        api.teams(params),
        api.staleSeats(),
        api.breakdowns(params),
        api.cost(params),
        api.aiCredits(params),
        api.models(params),
      ]);
      setState({
        loading: false,
        error: null,
        kpis,
        teams,
        stale,
        breakdowns,
        cost,
        premium,
        modelCreditsTotal: modelCreditsGrandTotal(models),
      });
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: (e as Error).message }));
    }
  }

  useEffect(() => {
    void load();
  }, [win.start, win.end]);

  return (
    <div>
      <DateRangeSelector value={win} onChange={setWin} />
      {state.error ? <div className="error">{state.error}</div> : null}
      {state.loading || !state.kpis ? (
        <div className="loading">Loading summary…</div>
      ) : (
        <>
          <KpiCards kpis={state.kpis} />

          {state.cost ? (
            <div className="panel">
              <h2>Cost for Window ({state.cost.window_days} days)</h2>
              <div className="kpi-grid">
                <Kpi
                  label="Window cost"
                  value={fmtMoney(state.cost.window_cost_usd)}
                  sub="actual consumption charges"
                  tooltip={
                    "Actual Copilot consumption cost for the selected window — sum of " +
                    "billing net_amount_usd across Copilot SKUs. GitHub bills Copilot per " +
                    "usage (AI credits), not a fixed per-seat price."
                  }
                />
                <Kpi
                  label="Monthly run-rate"
                  value={fmtMoney(state.cost.monthly_cost_usd)}
                  tooltip="Window consumption cost extrapolated to a 30-day run-rate. Not a fixed seat charge."
                />
                <Kpi
                  label="Lines accepted (window)"
                  value={state.kpis.lines_accepted_window.toLocaleString()}
                  tooltip={
                    "Sum of total_code_lines_accepted across every editor / model / language " +
                    "for each day in the window (Copilot Metrics API)."
                  }
                />
                <Kpi
                  label="Hours saved (window est.)"
                  value={state.kpis.hours_saved_30d.toLocaleString()}
                  sub={`${(60 * 0.5).toFixed(0)}s/acc benchmark`}
                  tooltip={
                    "Estimate: total_acceptances × MINUTES_SAVED_PER_ACCEPTANCE / 60. " +
                    "The benchmark (default 0.5 min/acceptance) is tunable via env."
                  }
                />
                <Kpi
                  label="AI credits"
                  value={
                    state.modelCreditsTotal !== null
                      ? fmtNum(state.modelCreditsTotal)
                      : state.premium
                        ? fmtNum(state.premium.total_ai_credits)
                        : "—"
                  }
                  sub={
                    state.premium && state.premium.available
                      ? fmtMoney(state.premium.total_ai_credit_cost_usd)
                      : "billing API unavailable"
                  }
                  tooltip={
                    "Total Copilot AI-credit quantity aligned to the Model Usage (Org) " +
                    "Per-Model Summary total. Sub-value is sum of net_amount_usd for " +
                    "billable Copilot SKUs from the billing API."
                  }
                />
              </div>

              {state.premium?.available ? (() => {
                const aiGross = state.premium!.skus.reduce((s, k) => s + k.gross_amount_usd, 0);
                const aiNet = state.premium!.total_ai_credit_cost_usd;
                const included = aiGross - aiNet;
                const licenses = state.cost!.window_cost_usd - aiNet;
                return (
                  <div style={{ marginTop: 16 }}>
                    <h3 className="subhead">Cost Breakdown</h3>
                    <p className="muted" style={{ marginBottom: 8 }}>
                      GitHub's billing page labels "Total gross spend on Copilot" as licenses + overage only
                      — not the true list-price gross. The breakdown below reconciles these figures.
                    </p>
                    <table>
                      <thead>
                        <tr>
                          <th>Line Item</th>
                          <th className="num-col">Amount</th>
                          <th>Notes</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>AI credits consumed</td>
                          <td className="num-col">{fmtNum(state.premium!.total_ai_credits)}</td>
                          <td className="muted">Total credits at list price</td>
                        </tr>
                        <tr>
                          <td>AI credits gross (list price)</td>
                          <td className="num-col">{fmtMoney(aiGross)}</td>
                          <td className="muted">All credits × $0.01</td>
                        </tr>
                        <tr style={{ color: "var(--color-success, #3fb950)" }}>
                          <td>Included usage discount</td>
                          <td className="num-col">−{fmtMoney(included)}</td>
                          <td className="muted">Credits covered by plan allowance</td>
                        </tr>
                        <tr>
                          <td>AI credits overage (net)</td>
                          <td className="num-col">{fmtMoney(aiNet)}</td>
                          <td className="muted">
                            {aiNet > 0
                              ? `~${fmtNum(Math.round(aiNet / 0.01))} credits beyond included`
                              : "All usage within included allowance"}
                          </td>
                        </tr>
                        <tr>
                          <td>Enterprise licenses</td>
                          <td className="num-col">{fmtMoney(licenses)}</td>
                          <td className="muted">Per-seat license fees (no discount)</td>
                        </tr>
                        <tr style={{ fontWeight: 600, borderTop: "2px solid var(--color-border, #444)" }}>
                          <td>Window cost (total billable)</td>
                          <td className="num-col">{fmtMoney(state.cost!.window_cost_usd)}</td>
                          <td className="muted">Licenses + AI overage = GitHub "gross spend"</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                );
              })() : null}
            </div>
          ) : null}

          <div className="panel">
            <h2>Breakdowns</h2>
            {state.breakdowns ? <BreakdownCharts data={state.breakdowns} /> : null}
          </div>

          <div className="row-grid">
            <div className="panel">
              <h2>Team Leaderboard — Top 10</h2>
              <TeamLeaderboard
                rows={[...state.teams]
                  .sort((a, b) => b.avg_active_users - a.avg_active_users)
                  .slice(0, 10)}
              />
            </div>
            <div className="panel">
              <h2>Stale Seats</h2>
              <StaleSeats seats={state.stale} />
            </div>
          </div>

          {state.premium?.top_users_per_model?.length ? (
            <div className="panel">
              <h2>Top 5 Users Per Model</h2>
              <TopUsersPerModelTable models={state.premium.top_users_per_model} />
            </div>
          ) : null}

          {state.premium?.balanced_users?.length ? (
            <div className="panel">
              <h2>Balanced Users</h2>
              <div className="muted" style={{ marginBottom: 8 }}>
                {`>=${state.premium.balanced_user_threshold_pct ?? 20}% high-tier and >=${state.premium.balanced_user_threshold_pct ?? 20}% low-tier models`}
              </div>
              <div className="muted" style={{ marginBottom: 8 }}>
                {`High-tier: ${(state.premium.balanced_user_high_tiers ?? ["Opus", "GPT-5.4/5.5", "Gemini Pro"]).join(", ")}`}
              </div>
              <div className="muted" style={{ marginBottom: 12 }}>
                {`Low-tier: ${(state.premium.balanced_user_low_tiers ?? ["Haiku", "Flash", "Auto:*", "Sonnet", "GPT-5.2/5.3", "Code Review"]).join(", ")}`}
              </div>
              <BalancedUsersTable users={state.premium.balanced_users} />
            </div>
          ) : null}

        </>
      )}
    </div>
  );
}
