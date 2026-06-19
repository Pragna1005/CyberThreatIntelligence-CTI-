const COLORS = {
  MITRE:     "bg-blue-600 text-white",
  ThreatFox: "bg-red-600 text-white",
  MSRC:      "bg-orange-500 text-white",
};

export default function SourceBadge({ source }) {
  const cls = COLORS[source] ?? "bg-gray-600 text-white";
  return (
    <span className={`text-xs font-bold px-2 py-0.5 rounded ${cls}`}>
      {source}
    </span>
  );
}
