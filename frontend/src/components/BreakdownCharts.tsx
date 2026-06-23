import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { type Breakdowns } from "../api";

interface Props {
  data: Breakdowns;
}

export function BreakdownCharts({ data }: Props): JSX.Element {
  return (
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
  );
}
