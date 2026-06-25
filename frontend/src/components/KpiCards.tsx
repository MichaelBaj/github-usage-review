import { type Kpis } from "../api";
import { Kpi } from "./TeamsTab";

interface Props {
  kpis: Kpis;
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function KpiCards({ kpis }: Props): JSX.Element {
  const cards: { label: string; value: string; sub?: string; tooltip: string }[] = [
    {
      label: "Total Seats",
      value: kpis.total_seats.toString(),
      sub: `${money(kpis.monthly_cost_usd)}/mo consumption run-rate`,
      tooltip:
        "Count of currently assigned Copilot seats in the org (from /copilot/billing/seats). " +
        "Sub-value is the monthly consumption run-rate: actual Copilot usage charges " +
        "(billing net_amount_usd) for the window, extrapolated to 30 days.",
    },
    {
      label: "Adoption (30d)",
      value: pct(kpis.adoption_rate_30d),
      sub: `${kpis.active_users_30d} active / ${kpis.total_seats} seats`,
      tooltip:
        "Share of assigned seats that had any Copilot activity in the last 30 days. " +
        "= active_users_30d / total_seats. Active = seat.last_activity_at within window.",
    },
    {
      label: "Acceptance Rate (30d)",
      value: pct(kpis.acceptance_rate_30d),
      sub: `${kpis.acceptances_30d.toLocaleString()} / ${kpis.suggestions_30d.toLocaleString()}`,
      tooltip:
        "Org-wide code-completion acceptance rate over the window. " +
        "= sum(total_code_acceptances) / sum(total_code_suggestions) across all editors, " +
        "models, and languages from the GitHub Copilot Metrics API.",
    },
  ];
  return (
    <div className="kpi-grid">
      {cards.map((c) => (
        <Kpi
          key={c.label}
          label={c.label}
          value={c.value}
          sub={c.sub}
          tooltip={c.tooltip}
        />
      ))}
    </div>
  );
}
