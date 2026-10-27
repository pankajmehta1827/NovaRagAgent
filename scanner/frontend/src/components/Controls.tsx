import type { RiskMode, ScanSettings, Universe } from "../types";

interface Props {
  settings: ScanSettings;
  universes: Universe[];
  loading: boolean;
  onChange: (s: ScanSettings) => void;
  onScan: (refresh: boolean) => void;
}

export function Controls({ settings, universes, loading, onChange, onScan }: Props) {
  const set = <K extends keyof ScanSettings>(k: K, v: ScanSettings[K]) => onChange({ ...settings, [k]: v });
  const numField = (k: "capital" | "max_loss" | "max_position_pct" | "min_score", label: string, step: number, hint?: string) => (
    <label className="field">
      <span>{label}</span>
      <input
        type="number"
        min={0}
        step={step}
        value={settings[k]}
        onChange={(e) => set(k, Number(e.target.value))}
      />
      {hint && <small>{hint}</small>}
    </label>
  );

  return (
    <form
      className="controls card"
      onSubmit={(e) => {
        e.preventDefault();
        onScan(false);
      }}
    >
      <label className="field">
        <span>Universe</span>
        <select value={settings.universe} onChange={(e) => set("universe", e.target.value)}>
          {universes.map((u) => (
            <option key={u.id} value={u.id}>
              {u.label}
            </option>
          ))}
        </select>
      </label>
      {numField("capital", "Capital (₹)", 10000)}
      {numField("max_loss", "Max loss / trade (₹)", 100, "loss at the stop")}
      {numField("max_position_pct", "Max position (%)", 1)}
      {numField("min_score", "Min score", 5, "out of 100")}
      <label className="field">
        <span>Market filter</span>
        <select value={settings.risk_mode} onChange={(e) => set("risk_mode", e.target.value as RiskMode)}>
          <option value="auto">Auto (from Nifty 500 trend)</option>
          <option value="on">Normal cutoff</option>
          <option value="off">Risk-off (+10 cutoff)</option>
        </select>
      </label>
      <div className="actions">
        <button type="submit" className="primary" disabled={loading}>
          {loading ? "Scanning…" : "Run scan"}
        </button>
        <button type="button" disabled={loading} onClick={() => onScan(true)} title="Ignore the 5-minute cache">
          Fresh data
        </button>
      </div>
    </form>
  );
}
