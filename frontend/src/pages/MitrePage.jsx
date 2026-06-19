import { useState } from "react";
import { api } from "../api";
import SearchBar from "../components/SearchBar";
import ResultCard from "../components/ResultCard";

const SUGGESTIONS = [
  "What techniques are used for lateral movement?",
  "How does credential dumping work?",
  "What is process injection?",
  "Phishing sub-techniques",
];

export default function MitrePage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult]   = useState(null);
  const [error, setError]     = useState(null);

  async function handleSearch(query) {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.mitre(query));
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
          <span className="text-blue-400">MITRE ATT&CK</span> Intelligence
        </h1>
        <p className="text-gray-400 text-sm">
          Search attack techniques, tactics, and sub-techniques
        </p>
      </div>

      <SearchBar
        onSearch={handleSearch}
        loading={loading}
        placeholder="e.g. What techniques are used for privilege escalation?"
      />

      <div className="flex flex-wrap gap-2 mt-3">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => handleSearch(s)}
            className="text-xs px-3 py-1 rounded-full border border-blue-800
                       text-blue-400 hover:bg-blue-900/40 transition-colors"
          >
            {s}
          </button>
        ))}
      </div>

      {loading && (
        <div className="mt-10 text-center text-gray-400 animate-pulse">
          Searching MITRE ATT&CK knowledge base...
        </div>
      )}

      {error && (
        <div className="mt-6 p-4 bg-red-900/40 border border-red-700 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-8 space-y-6">
          <div className="bg-gray-800 border border-blue-900 rounded-xl p-6">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-blue-400 font-semibold text-sm">Answer</span>
              <span className="text-xs text-gray-500">· {result.model}</span>
            </div>
            <p className="text-gray-200 text-sm leading-relaxed whitespace-pre-wrap">
              {result.answer}
            </p>
          </div>

          <div>
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
              Matched Techniques ({result.sources.length})
            </h2>
            <div className="space-y-3">
              {result.sources.map((s) => (
                <ResultCard key={s.chunk_id} {...s} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
