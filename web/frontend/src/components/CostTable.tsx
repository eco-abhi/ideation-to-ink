import type { CostsResponse } from "../api";

interface Props {
  costs: CostsResponse;
}

export function CostTable({ costs }: Props) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "1px solid var(--gridline)" }}>
          <th style={{ padding: "4px 8px" }}>Agent</th>
          <th style={{ padding: "4px 8px", textAlign: "right" }}>Calls</th>
          <th style={{ padding: "4px 8px", textAlign: "right" }}>Prompt</th>
          <th style={{ padding: "4px 8px", textAlign: "right" }}>Completion</th>
          <th style={{ padding: "4px 8px", textAlign: "right" }}>Cost (USD)</th>
        </tr>
      </thead>
      <tbody>
        {costs.rows.map((row) => (
          <tr key={row.key} style={{ borderBottom: "1px solid var(--gridline)" }}>
            <td style={{ padding: "4px 8px" }}>{row.key}</td>
            <td style={{ padding: "4px 8px", textAlign: "right" }}>{row.calls}</td>
            <td style={{ padding: "4px 8px", textAlign: "right" }}>{row.prompt_tokens.toLocaleString()}</td>
            <td style={{ padding: "4px 8px", textAlign: "right" }}>{row.completion_tokens.toLocaleString()}</td>
            <td style={{ padding: "4px 8px", textAlign: "right" }}>
              ${row.cost_usd.toFixed(4)}
              {row.cost_unknown_calls > 0 && (
                <span title={`${row.cost_unknown_calls} call(s) with unknown pricing, excluded`}> *</span>
              )}
            </td>
          </tr>
        ))}
        {costs.rows.length === 0 && (
          <tr>
            <td colSpan={5} style={{ padding: 12, color: "var(--text-muted)", textAlign: "center" }}>
              No LLM usage recorded yet.
            </td>
          </tr>
        )}
      </tbody>
      {costs.rows.length > 0 && (
        <tfoot>
          <tr style={{ fontWeight: 600, borderTop: "2px solid var(--gridline)" }}>
            <td style={{ padding: "4px 8px" }}>Total</td>
            <td style={{ padding: "4px 8px", textAlign: "right" }}>{costs.total.calls}</td>
            <td style={{ padding: "4px 8px", textAlign: "right" }}>{costs.total.prompt_tokens.toLocaleString()}</td>
            <td style={{ padding: "4px 8px", textAlign: "right" }}>
              {costs.total.completion_tokens.toLocaleString()}
            </td>
            <td style={{ padding: "4px 8px", textAlign: "right" }}>${costs.total.cost_usd.toFixed(4)}</td>
          </tr>
        </tfoot>
      )}
    </table>
  );
}
