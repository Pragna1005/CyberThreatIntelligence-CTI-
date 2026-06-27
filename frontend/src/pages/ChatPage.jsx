import { useState } from "react";
import { api } from "../api";
import SearchBar from "../components/SearchBar";
import ResultCard from "../components/ResultCard";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function ChatPage() {
  const [loading, setLoading]   = useState(false);
  const [result, setResult]     = useState(null);
  const [error, setError]       = useState(null);

  async function handleSearch(query) {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.chat(query);
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-white mb-2">
          Cyber Threat Intelligence Bot
        </h1>
        <p className="text-gray-400 text-sm">
          Searches across MITRE ATT&CK · CERT Advisories · ThreatFox IOCs
        </p>
      </div>

      <SearchBar
        onSearch={handleSearch}
        loading={loading}
        placeholder="e.g. Tell me about phishing threats targeting Microsoft..."
      />

      {loading && (
        <div className="mt-10 text-center text-gray-400 animate-pulse">
          Retrieving intelligence and generating answer...
        </div>
      )}

      {error && (
        <div className="mt-6 p-4 bg-red-900/40 border border-red-700 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-8 space-y-6">
          <div className="bg-gray-800 border border-gray-700 rounded-xl p-6">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-purple-400 font-semibold text-sm">Answer</span>
              <span className="text-xs text-gray-500">· {result.model}</span>
            </div>
            <div className="text-gray-200 text-sm leading-relaxed prose prose-invert prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {result.answer}
              </ReactMarkdown>
            </div>
          </div>

          <div>
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
              Retrieved Sources ({result.sources.length})
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
