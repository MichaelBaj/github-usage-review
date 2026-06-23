import { type StaleSeat } from "../api";

interface Props {
  seats: StaleSeat[];
}

export function StaleSeats({ seats }: Props): JSX.Element {
  if (seats.length === 0) {
    return <div className="loading">No stale seats — every assigned seat is active.</div>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>User</th>
          <th>Team</th>
          <th>Last Activity</th>
          <th>Days Inactive</th>
          <th>Last Editor</th>
        </tr>
      </thead>
      <tbody>
        {seats.map((s) => (
          <tr key={s.login}>
            <td>{s.login}</td>
            <td>{s.team ?? "—"}</td>
            <td>{s.last_activity_at ?? "never"}</td>
            <td>{s.days_inactive ?? "—"}</td>
            <td>{s.editor ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
