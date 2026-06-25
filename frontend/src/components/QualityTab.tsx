import { useEffect, useState } from "react";
import { api, type QualitySummary } from "../api";
import {
  defaultWindow,
  DateRangeSelector,
  toWindowParams,
  type WindowState,
} from "./DateRangeSelector";
import { fmtNum, fmtPct, Kpi, ModelSummaryTable, CodeEditorTable, PrCorrelationTable, fmtMoney } from "./TeamsTab";

export function QualityTab(): JSX.Element {
  const [win, setWin] = useState<WindowState>(defaultWindow(30));
  const [data, setData] = useState<QualitySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    api
      .quality(toWindowParams(win))
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [win.start, win.end]);

  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="loading">Loading quality view…</div>;

  const cvi = data.chat_vs_inline;
  const pu = data.power_users;
  const cr = data.cohort_ramp;

  return (
    <div>
      <DateRangeSelector value={win} onChange={setWin} />

      <div className="panel">
        <h2>Chat vs Inline (Org)</h2>
        <div className="kpi-grid">
          <Kpi
            label="Code suggestions"
            value={cvi.code_suggestions.toLocaleString()}
            sub={`acc rate ${fmtPct(cvi.code_acceptance_rate)}`}
            tooltip={
              "Sum of total_code_suggestions across every editor / model / language in the window " +
              "(Copilot Metrics API). Sub-value is overall acceptance rate."
            }
          />
          <Kpi
            label="Code acceptances"
            value={cvi.code_acceptances.toLocaleString()}
            sub={`${cvi.code_lines_accepted.toLocaleString()} lines`}
            tooltip={
              "Sum of total_code_acceptances in the window. Sub-value is total_code_lines_accepted — " +
              "acceptances counts events, lines counts the volume of code accepted."
            }
          />
          <Kpi
            label="Chat interactions"
            value={cvi.chat_total.toLocaleString()}
            sub={`${cvi.chat_insertions} insertions`}
            tooltip={
              "Sum of total_chats across all chat editors / models in the window. " +
              "Insertions = code inserted from chat into the editor."
            }
          />
          <Kpi
            label="Chat share of interactions"
            value={fmtPct(cvi.chat_interaction_share)}
            tooltip={
              "Share of total Copilot interactions that are chat (not inline completions). " +
              "= chat_total / (chat_total + code_acceptances). Higher = more chat-driven workflow."
            }
          />
        </div>
      </div>

      <div className="panel">
        <h2>Model Usage (Org)</h2>
        <ModelSummaryTable data={data.model_breakdown} />
        <CodeEditorTable rows={data.model_breakdown.code_editors} />
      </div>

      <div className="panel">
        <h2>Power-User Concentration</h2>
        <div className="kpi-grid">
          <Kpi
            label="Active authors"
            value={pu.active_authors.toLocaleString()}
            sub={`${pu.total_prs.toLocaleString()} PRs`}
            tooltip={
              "Distinct PR authors with at least one PR in the window. " +
              "Sub-value is total PR count in the same window."
            }
          />
          <Kpi
            label="Top-10% share of PRs"
            value={fmtPct(pu.top_10pct_share)}
            sub="lower = more even"
            tooltip={
              "Share of total PRs written by the top 10% of authors (by PR count). " +
              "= sum(prs in top decile) / total_prs. " +
              "100% = one author wrote everything; 10% = perfectly even distribution."
            }
          />
          <Kpi
            label="Median PRs / user"
            value={pu.median_prs_per_user.toLocaleString()}
            tooltip={
              "Median PR count per active author. " +
              "More robust than mean to power-user skew."
            }
          />
        </div>
        <h3 className="subhead">Top Contributors</h3>
        <table>
          <thead>
            <tr>
              <th>User</th>
              <th>PRs</th>
              <th>+lines</th>
              <th>-lines</th>
              <th>Seat?</th>
            </tr>
          </thead>
          <tbody>
            {pu.top_users.map((u) => (
              <tr key={u.login}>
                <td>{u.login}</td>
                <td>{fmtNum(u.prs)}</td>
                <td>{fmtNum(u.additions)}</td>
                <td>{fmtNum(u.deletions)}</td>
                <td>{u.has_seat ? "yes" : "no"}</td>
              </tr>
            ))}
            {pu.top_users.length === 0 ? (
              <tr>
                <td colSpan={5} className="muted">
                  No PR data in window. Run a snapshot with PR ingestion enabled.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2>Seat Onboarding Ramp</h2>
        <div className="kpi-grid">
          <Kpi
            label="Median days to first use"
            value={cr.median_days_to_first_use === null ? "—" : String(cr.median_days_to_first_use)}
            sub={`${cr.sample_size} seats sampled`}
            tooltip={
              "Median days between seat created_at and last_activity_at across seats that have been used. " +
              "Lower = faster onboarding ramp."
            }
          />
          <Kpi
            label="≤ 7 days"
            value={String(cr.buckets["<=7d"] ?? 0)}
            tooltip="Seats whose first activity was within 7 days of assignment. Fastest-ramp cohort."
          />
          <Kpi
            label="8 – 14 days"
            value={String(cr.buckets["8-14d"] ?? 0)}
            tooltip="Seats whose first activity occurred 8–14 days after assignment."
          />
          <Kpi
            label="15 – 30 days"
            value={String(cr.buckets["15-30d"] ?? 0)}
            tooltip="Seats whose first activity occurred 15–30 days after assignment."
          />
          <Kpi
            label="> 30 days"
            value={String(cr.buckets[">30d"] ?? 0)}
            tooltip="Seats that took more than 30 days to first use. Slow-ramp cohort."
          />
          <Kpi
            label="Never used"
            value={String(cr.never_used)}
            tooltip="Seats with last_activity_at = null. Immediate reclaim candidates."
          />
        </div>
      </div>

      <div className="panel">
        <h2>PR Correlation</h2>
        <PrCorrelationTable c={data.pr_correlation} />
      </div>

      <div className="panel">
        <h2>AI Credit Usage (Org, Billing-Derived)</h2>
        <div className="muted" style={{ marginBottom: 8 }}>
          <strong>Tokens:</strong> {data.ai_credits.tokens_note}
        </div>
        {!data.ai_credits.available ? (
          <div className="muted">
            No billing-usage rows for this window. The enhanced-billing API may not be enabled for
            this org tier, or the token lacks <code>Plan: Read</code>.
          </div>
        ) : (
          <>
            <div className="kpi-grid">
              <Kpi
                label="AI credits (window)"
                value={fmtNum(data.ai_credits.total_ai_credits)}
                tooltip={
                  "Sum of billable Copilot SKU quantity across the org for the window " +
                  "(enhanced-billing API)."
                }
              />
              <Kpi
                label="Cost (window)"
                value={fmtMoney(data.ai_credits.total_ai_credit_cost_usd)}
                tooltip={
                  "Sum of net_amount_usd (gross − discount) for billable Copilot SKUs in the window."
                }
              />
            </div>
            <h3 className="subhead">By Billable SKU</h3>
            <table>
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Product</th>
                  <th>Quantity</th>
                  <th>Gross</th>
                  <th>Net</th>
                </tr>
              </thead>
              <tbody>
                {data.ai_credits.skus.map((s) => (
                  <tr key={`${s.product}/${s.sku}`}>
                    <td>{s.sku}</td>
                    <td>{s.product}</td>
                    <td>{fmtNum(s.quantity)}</td>
                    <td>{fmtMoney(s.gross_amount_usd)}</td>
                    <td>{fmtMoney(s.net_amount_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h3 className="subhead" style={{ marginTop: 16 }}>
              Top Users by AI Credits
            </h3>
            <table>
              <thead>
                <tr>
                  <th>User</th>
                  <th>AI Credits</th>
                  <th>Gross</th>
                  <th>Net</th>
                </tr>
              </thead>
              <tbody>
                {data.ai_credits.top_users.map((u) => (
                  <tr key={u.login}>
                    <td>{u.login}</td>
                    <td>{fmtNum(u.ai_credits)}</td>
                    <td>{fmtMoney(u.gross_amount_usd)}</td>
                    <td>{fmtMoney(u.net_amount_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
