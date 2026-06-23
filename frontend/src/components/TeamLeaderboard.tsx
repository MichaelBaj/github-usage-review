import { type TeamRow } from "../api";

interface Props {
  rows: TeamRow[];
}

export function TeamLeaderboard({ rows }: Props): JSX.Element {
  if (rows.length === 0) {
    return <div className="loading">No team-level data yet.</div>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>Team</th>
          <th>Members</th>
          <th>Active</th>
          <th>Adoption</th>
          <th>PRs</th>
          <th>Merged PRs</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.team}>
            <td>{r.team}</td>
            <td>{r.members_with_seats} / {r.members_total}</td>
            <td>{r.active_members}</td>
            <td>{(r.adoption_rate * 100).toFixed(1)}%</td>
            <td>{r.prs.toLocaleString()}</td>
            <td>{r.merged_prs.toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
