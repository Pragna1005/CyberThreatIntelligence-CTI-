import { useState, useRef, useEffect } from "react";
import { api } from "../api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ResultCard from "../components/ResultCard";

function UserBubble({ text }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] bg-blue-600 text-white rounded-2xl rounded-br-sm px-4 py-3 text-sm leading-relaxed">
        {text}
      </div>
    </div>
  );
}

function AssistantBubble({ answer, sources, model, loading }) {
  const [showSources, setShowSources] = useState(false);

  if (loading) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[75%] bg-gray-800 border border-gray-700 rounded-2xl rounded-bl-sm px-4 py-3">
          <div className="flex gap-1 items-center h-5">
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] space-y-2">
        <div className="bg-gray-800 border border-gray-700 rounded-2xl rounded-bl-sm px-4 py-3">
          <div className="prose prose-invert prose-sm max-w-none text-gray-200">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
          </div>
          {model && (
            <p className="text-xs text-gray-500 mt-2">{model}</p>
          )}
        </div>

        {sources && sources.length > 0 && (
          <div>
            <button
              onClick={() => setShowSources((v) => !v)}
              className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              {showSources ? "Hide" : "Show"} {sources.length} source{sources.length !== 1 ? "s" : ""}
            </button>
            {showSources && (
              <div className="mt-2 space-y-2">
                {sources.map((s) => (
                  <ResultCard key={s.chunk_id} {...s} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState(() => {
    try {
      const saved = localStorage.getItem("cti_chat_history");
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [loading, setLoading] = useState(false);
  const [input, setInput] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    localStorage.setItem("cti_chat_history", JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend() {
    const query = input.trim();
    if (!query || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: query }]);
    setLoading(true);

    try {
      const data = await api.chat(query);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", answer: data.answer, sources: data.sources, model: data.model },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", answer: `Error: ${e.message}`, sources: [], model: null },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleClear() {
    setMessages([]);
    localStorage.removeItem("cti_chat_history");
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-64px)] max-w-4xl mx-auto px-4">
      {messages.length === 0 && !loading && (
        <div className="flex-1 flex flex-col items-center justify-center text-center gap-3">
          <h1 className="text-3xl font-bold text-white">Cyber Threat Intelligence Bot</h1>
          <p className="text-gray-400 text-sm">
            Searches across MITRE ATT&CK · CERT Advisories · ThreatFox IOCs
          </p>
          <p className="text-gray-600 text-xs mt-2">Ask a question below to get started.</p>
        </div>
      )}

      {messages.length > 0 && (
        <div className="flex-1 overflow-y-auto py-6 space-y-4">
          <div className="flex justify-end">
            <button
              onClick={handleClear}
              className="text-xs text-gray-500 hover:text-red-400 transition-colors"
            >
              Clear chat
            </button>
          </div>
          {messages.map((msg, i) =>
            msg.role === "user" ? (
              <UserBubble key={i} text={msg.text} />
            ) : (
              <AssistantBubble
                key={i}
                answer={msg.answer}
                sources={msg.sources}
                model={msg.model}
              />
            )
          )}
          {loading && <AssistantBubble loading />}
          <div ref={bottomRef} />
        </div>
      )}

      {messages.length === 0 && <div className="flex-1" />}

      <div className="py-4">
        <div className="flex gap-2 items-end bg-gray-800 border border-gray-700 rounded-2xl px-4 py-3 focus-within:border-blue-500 transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a threat intelligence question... (Enter to send, Shift+Enter for newline)"
            rows={1}
            className="flex-1 bg-transparent text-white placeholder-gray-500 text-sm resize-none outline-none max-h-40 leading-relaxed"
            style={{ fieldSizing: "content" }}
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="flex-shrink-0 px-4 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700
                       disabled:text-gray-500 text-white rounded-xl font-medium text-sm transition-colors"
          >
            {loading ? "..." : "Send"}
          </button>
        </div>
        <p className="text-center text-xs text-gray-600 mt-2">
          Answers are grounded in retrieved knowledge base context only.
        </p>
      </div>
    </div>
  );
}
