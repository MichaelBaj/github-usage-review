import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import { type TrendPoint } from "../api";

interface Props {
  data: TrendPoint[];
}

export function TrendChart({ data }: Props): JSX.Element {
  if (data.length === 0) {
    return <div className="loading">No trend data yet — snapshots will populate this view.</div>;
  }
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
        <XAxis dataKey="date" stroke="#8b949e" fontSize={11} />
        <YAxis yAxisId="left" stroke="#8b949e" fontSize={11} />
        <YAxis
          yAxisId="right"
          orientation="right"
          stroke="#8b949e"
          fontSize={11}
          domain={[0, 1]}
          tickFormatter={(v) => `${Math.round(v * 100)}%`}
        />
        <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #30363d" }} />
        <Legend />
        <Line yAxisId="left" type="monotone" dataKey="active_users" stroke="#58a6ff" name="DAU" dot={false} />
        <Line
          yAxisId="left"
          type="monotone"
          dataKey="acceptances"
          stroke="#3fb950"
          name="Acceptances"
          dot={false}
        />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="acceptance_rate"
          stroke="#d29922"
          name="Acceptance rate"
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
