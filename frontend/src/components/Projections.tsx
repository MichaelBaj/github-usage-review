import { type Projections } from "../api";

interface Props {
  data: Projections;
}

export function ProjectionsView({ data }: Props): JSX.Element {
  if (!data.available) {
    return <div className="loading">Projections unavailable: {data.reason ?? "insufficient data"}</div>;
  }
  return (
    <table>
      <tbody>
        <tr>
          <td>History collected</td>
          <td>{data.history_days} days</td>
        </tr>
        <tr>
          <td>Current active users</td>
          <td>{data.current_active}</td>
        </tr>
        <tr>
          <td>Projected active users (90d)</td>
          <td>{data.projected_active_90d}</td>
        </tr>
        <tr>
          <td>Trend slope (users/day)</td>
          <td>{data.trend_slope_per_day}</td>
        </tr>
        <tr>
          <td>Current seats</td>
          <td>{data.current_seats}</td>
        </tr>
        <tr>
          <td>Recommended seats (80% target adoption)</td>
          <td>{data.recommended_seats_for_80pct_adoption}</td>
        </tr>
        <tr>
          <td>Potential seat reduction</td>
          <td>{data.potential_seat_reduction}</td>
        </tr>
      </tbody>
    </table>
  );
}
