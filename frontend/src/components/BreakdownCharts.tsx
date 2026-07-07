import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { type Breakdowns, type FeatureBreakdown, type AiCreditsProjection } from "../api";

interface Props {
  data: Breakdowns;
  features?: FeatureBreakdown | null;
  creditProjection?: AiCreditsProjection | null;
}

function featureLabel(f: string): string {
  return f
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function BreakdownCharts({ data, features, creditProjection }: Props): JSX.Element {
  // Merge current and previous month points into a single array keyed by day.
  const projectionData = (() => {
    if (!creditProjection) return null;
    const { current_month, previous_month } = creditProjection;
    if (current_month.length === 0 && previous_month.length === 0) return null;
    const maxDay = Math.max(
      current_month.length > 0 ? current_month[current_month.length - 1].day : 0,
      previous_month.length > 0 ? previous_month[previous_month.length - 1].day : 0,
    );
    const curByDay: Record<number, number> = {};
    for (const pt of current_month) curByDay[pt.day] = pt.cumulative;
    const prevByDay: Record<number, number> = {};
    for (const pt of previous_month) prevByDay[pt.day] = pt.cumulative;
    return Array.from({ length: maxDay }, (_, i) => {
      const day = i + 1;
      const row: Record<string, number> = { day };
      if (curByDay[day] !== undefined) row.current = curByDay[day];
      if (prevByDay[day] !== undefined) row.previous = prevByDay[day];
      return row;
    });
  })();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", flexDirection: "row", gap: 24 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ margin: "0 0 8px 0", fontSize: 14, color: "#8b949e" }}>Top Languages</h3>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={data.languages.slice(0, 10)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="language" stroke="#8b949e" fontSize={11} angle={-35} textAnchor="end" height={70} interval={0} />
              <YAxis stroke="#8b949e" fontSize={11} />
              <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #30363d" }} />
              <Bar dataKey="acc" fill="#58a6ff" name="Acceptances" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ margin: "0 0 8px 0", fontSize: 14, color: "#8b949e" }}>Models</h3>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={(data.models || []).slice(0, 10)} barCategoryGap="20%">
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="model" stroke="#8b949e" fontSize={11} angle={-35} textAnchor="end" height={70} interval={0} tickLine={false} />
              <YAxis stroke="#8b949e" fontSize={11} label={{ value: "Requests", angle: -90, position: "insideLeft", style: { fill: "#8b949e", fontSize: 11 } }} />
              <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #30363d" }} />
              <Bar dataKey="sug" fill="#bc8cff" name="Code requests" stackId="a" />
              <Bar dataKey="chats" fill="#d29922" name="Chat requests" stackId="a" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "row", gap: 24 }}>
        {projectionData && creditProjection && (
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3 style={{ margin: "0 0 4px 0", fontSize: 14, color: "#8b949e" }}>
              AI Credit Usage — Month over Month
            </h3>
            {creditProjection.current_month.length === 0 && (
              <p style={{ margin: "0 0 8px 0", fontSize: 12, color: "#6e7681" }}>
                No billing data for {creditProjection.current_month_label} yet — run a snapshot or import a billing CSV to populate the current month line.
              </p>
            )}
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={projectionData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                <XAxis
                  dataKey="day"
                  stroke="#8b949e"
                  fontSize={11}
                  label={{ value: "Day of month", position: "insideBottomRight", offset: -4, style: { fill: "#8b949e", fontSize: 11 } }}
                />
                <YAxis stroke="#8b949e" fontSize={11} />
                <Tooltip
                  contentStyle={{ background: "#161b22", border: "1px solid #30363d", fontSize: 12 }}
                  labelFormatter={(label) => `Day ${label}`}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: "#8b949e" }} />
                <Line
                  type="monotone"
                  dataKey="current"
                  stroke="#58a6ff"
                  strokeWidth={2}
                  dot={false}
                  name={creditProjection.current_month_label}
                  connectNulls={false}
                />
                <Line
                  type="monotone"
                  dataKey="previous"
                  stroke="#8b949e"
                  strokeWidth={2}
                  strokeDasharray="5 3"
                  dot={false}
                  name={creditProjection.previous_month_label}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        {features && features.features.length > 0 && (
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3 style={{ margin: "0 0 8px 0", fontSize: 14, color: "#8b949e" }}>
              Feature Usage
            </h3>
            <ResponsiveContainer width="100%" height={320}>
              <BarChart
                data={features.features.map((f) => ({
                  ...f,
                  label: featureLabel(f.feature),
                }))}
                barCategoryGap="20%"
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                <XAxis dataKey="label" stroke="#8b949e" fontSize={11} angle={-35} textAnchor="end" height={90} interval={0} />
                <YAxis stroke="#8b949e" fontSize={11} />
                <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #30363d" }} />
                <Bar dataKey="interactions" fill="#f78166" name="Interactions" stackId="a" />
                <Bar dataKey="code_generations" fill="#58a6ff" name="Code generated" stackId="a" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}
