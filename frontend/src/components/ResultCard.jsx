import SourceBadge from "./SourceBadge";

export default function ResultCard({ source, chunk_id, score, text_preview }) {
  return (
    <div className="border border-gray-700 rounded-lg p-4 bg-gray-800 hover:border-gray-500 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <SourceBadge source={source} />
          <code className="text-xs text-gray-400">{chunk_id}</code>
        </div>
        <span className="text-xs text-green-400 font-mono">
          score: {score.toFixed(3)}
        </span>
      </div>
      <p className="text-sm text-gray-300 leading-relaxed line-clamp-3">
        {text_preview}
      </p>
    </div>
  );
}
