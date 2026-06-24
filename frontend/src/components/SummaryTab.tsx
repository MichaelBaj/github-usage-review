import { useEffect, useState } from "react";
import {
  api,
  type Breakdowns,
  type CostWindow,
  type Kpis,
  type AiCreditsSummary,
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
};

export function SummaryTab(): JSX.Element {
  const [win, setWin] = useState<WindowState>(defaultWindow(30));
  const [state, setState] = useState<State>(initial);

  async function load(): Promise<void> {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const params = toWindowParams(win);
      const [kpis, teams, stale, breakdowns, cost, premium] = await Promise.all([
        api.kpis(params),
        api.teams(params),
        api.staleSeats(),
        api.breakdowns(params),
        api.cost(params),
        api.aiCredits(params),
      ]);
      setState({ loading: false, error: null, kpis, teams, stale, breakdowns, cost, premium });
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
                  value={state.premium ? fmtNum(state.premium.total_ai_credits) : "—"}
                  sub={
                    state.premium && state.premium.available
                      ? fmtMoney(state.premium.total_ai_credit_cost_usd)
                      : "billing API unavailable"
                  }
                  tooltip={
                    "Total Copilot AI-credit quantity in the window from the enhanced-billing " +
                    "API. Sub-value is sum of net_amount_usd for billable Copilot SKUs. " +
                    "Requires Plan: Read on the org token."
                  }
                />
              </div>
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


        </>
      )}
    </div>
  );
}
