// Phase 18c — Frequency caps editor for the campaign wizard.
const _LABELS = {
  min_seconds_between:           ["Min seconds between", 600],
  max_impressions_per_hour:      ["Max per hour",            3],
  max_impressions_per_day:       ["Max per day",              10],
  max_per_advertiser_per_week: ["Max per advertiser / week", 50],
  max_per_channel_cadence:      ["Min songs between (channel cadence)", 4],
};

export default function FreqCapsEditor({ value, onChange }) {
  const v = value || {};
  const set = (k, n) => onChange({ ...v, [k]: parseInt(n) || 0 });
  return (
    <div className="space-y-2" data-testid="freq-caps-editor">
      {Object.entries(_LABELS).map(([k, [label, def]]) => (
        <label key={k} className="flex justify-between items-center text-sm">
          <span className="text-text-secondary">{label}</span>
          <input type="number" data-testid={`cap-${k}`}
                      defaultValue={v[k] ?? def}
                      onChange={(e) => set(k, e.target.value)}
                      className="bigfm-input w-24 text-right" />
        </label>
      ))}
    </div>
  );
}
