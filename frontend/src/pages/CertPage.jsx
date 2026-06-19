import { useState } from "react";
import { api } from "../api";
import SearchBar from "../components/SearchBar";
import ResultCard from "../components/ResultCard";

const SUGGESTIONS = [
  "Critical Windows vulnerabilities",
  "Microsoft Office high severity CVEs",
  "Vulnerabilities with active exploitation",
  "Windows Kernel security flaws",
];

const SEVERITY_COLOR = {
  Critical: "text-red-400 bg-red-900/30 border-red-800",
  High:     "text-orange-400 bg-orange-900/30 border-orange-800",
  Medium:   "text-yellow-400 bg-yellow-900/30 border-yellow-800",
  Low:      "text-green-400 bg-green-900/30 border-green-800",
};

function SeverityPill({ text }) {
  const level = ["Critical","High","Medium","Low"].find((l) =>
    text?.includes(l)
  );
  const cls = SEVERITY_COLOR[level] ?? "text-gray-400 bg-gray-800 border-gray-700";
  return level ? (
    <span className={`text-xs font-bold px-2 py-0.5 rounded border ${cls}`}>
      {level}
    </span>
  ) : null;
}

export default function CertPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult]   = useState(null);
  const [error, setError]     = useState(null);

  async function handleSearch(query) {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.cert(query));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white mb-1">
          <span className="text-orange-400">CERT</span> Advisory Search
        </h1>
        <p className="text-gray-400 text-sm">
          Search Microsoft security advisories and CVE records
        </p>
      </div>

      <SearchBar
        onSearch={handleSearch}
        loading={loading}
        placeholder="e.g. Critical vulnerabilities in Windows HTTP.sys..."
      />

      <div className="flex flex-wrap gap-2 mt-3">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => handleSearch(s)}
            className="text-xs px-3 py-1 rounded-full border border-orange-800
                       text-orange-400 hover:bg-orange-900/40 transition-colors"
          >
            {s}
          </button>
        ))}
      </div>

      {loading && (
        <div className="mt-10 text-center text-gray-400 animate-pulse">
          Searching CERT advisory database...
        </div>
      )}

      {error && (
        <div className="mt-6 p-4 bg-red-900/40 border border-red-700 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-8 space-y-6">
          <div className="bg-gray-800 border border-orange-900 rounded-xl p-6">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-orange-400 font-semibold text-sm">Answer</span>
              <span className="text-xs text-gray-500">· {result.model}</span>
            </div>
            <p className="text-gray-200 text-sm leading-relaxed whitespace-pre-wrap">
              {result.answer}
            </p>
          </div>

          <div>
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
              Matched Advisories ({result.sources.length})
            </h2>
            <div className="space-y-3">
              {result.sources.map((s) => (
                <div key={s.chunk_id} className="flex items-start gap-2">
                  <SeverityPill text={s.text_preview} />
                  <div className="flex-1">
                    <ResultCard {...s} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
