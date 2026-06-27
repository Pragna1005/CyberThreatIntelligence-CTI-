import { useState, useRef, useEffect } from "react";
import { api } from "../api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ResultCard from "../components/ResultCard";

const SUGGESTIONS = [
  "What techniques are used for lateral movement?",
  "How does credential dumping work?",
  "What is process injection?",
  "Phishing sub-techniques",
];

// ── Storage helpers ───────────────────────────────────────────────────────────

function loadConversations() {
  try { return JSON.parse(localStorage.getItem("cti_mitre_conversations") || "[]"); }
  catch { return []; }
}

function saveConversations(convs) {
  localStorage.setItem("cti_mitre_conversations", JSON.stringify(convs));
}

function makeConversation() {
  return { id: String(Date.now()), title: "New Chat", messages: [], createdAt: Date.now() };
}

// ── Bubble components ─────────────────────────────────────────────────────────

function UserBubble({ text }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] bg-blue-700 text-white rounded-2xl rounded-br-sm px-4 py-3 text-sm leading-relaxed">
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
        <div className="bg-gray-800 border border-blue-900 rounded-2xl rounded-bl-sm px-4 py-3">
          <div className="flex gap-1 items-center h-5">
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce [animation-delay:0ms]" />
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce [animation-delay:150ms]" />
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce [animation-delay:300ms]" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] space-y-2">
        <div className="bg-gray-800 border border-blue-900 rounded-2xl rounded-bl-sm px-4 py-3">
          <div className="prose prose-invert prose-sm max-w-none text-gray-200">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
          </div>
          {model && <p className="text-xs text-gray-500 mt-2">{model}</p>}
        </div>
        {sources && sources.length > 0 && (
          <div>
            <button
              onClick={() => setShowSources((v) => !v)}
              className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              {showSources ? "Hide" : "Show"} {sources.length} technique{sources.length !== 1 ? "s" : ""}
            </button>
            {showSources && (
              <div className="mt-2 space-y-2">
                {sources.map((s) => <ResultCard key={s.chunk_id} {...s} />)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

function Sidebar({ conversations, activeId, onSelect, onNew, onDelete }) {
  return (
    <aside className="w-64 flex-shrink-0 bg-gray-900 border-r border-gray-700 flex flex-col h-full">
      <div className="p-3 border-b border-gray-700">
        <button
          onClick={onNew}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-gray-300
                     hover:bg-gray-700 border border-gray-600 hover:border-gray-500 transition-colors"
        >
          <span className="text-lg leading-none">+</span>
          New Search
        </button>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {conversations.length === 0 && (
          <p className="text-xs text-gray-600 text-center mt-6 px-4">No searches yet</p>
        )}
        {[...conversations].reverse().map((conv) => (
          <div
            key={conv.id}
            className={`group flex items-center gap-2 mx-2 mb-1 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors ${
              conv.id === activeId
                ? "bg-gray-700 text-white"
                : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
            }`}
            onClick={() => onSelect(conv.id)}
          >
            <span className="flex-1 truncate">{conv.title}</span>
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(conv.id); }}
              className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-all text-xs flex-shrink-0"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
      <div className="p-3 border-t border-gray-700">
        <p className="text-xs text-gray-600 text-center">
          MITRE · {conversations.length} session{conversations.length !== 1 ? "s" : ""}
        </p>
      </div>
    </aside>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function MitrePage() {
  const [conversations, setConversations] = useState(loadConversations);
  const [activeId, setActiveId] = useState(() => {
    const convs = loadConversations();
    const savedId = localStorage.getItem("cti_mitre_active_id");
    if (savedId && convs.find((c) => c.id === savedId)) return savedId;
    return convs.length > 0 ? convs[convs.length - 1].id : null;
  });
  const [loading, setLoading] = useState(false);
  const [input, setInput] = useState("");
  const bottomRef = useRef(null);

  const activeConversation = conversations.find((c) => c.id === activeId) || null;
  const messages = activeConversation?.messages || [];

  useEffect(() => { saveConversations(conversations); }, [conversations]);
  useEffect(() => {
    if (activeId) localStorage.setItem("cti_mitre_active_id", activeId);
    else localStorage.removeItem("cti_mitre_active_id");
  }, [activeId]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  function updateConversation(id, updater) {
    setConversations((prev) => prev.map((c) => (c.id === id ? updater(c) : c)));
  }

  async function handleSend(query) {
    const q = (query ?? input).trim();
    if (!q || loading) return;
    setInput("");

    let convId = activeId;
    if (!convId || !conversations.find((c) => c.id === convId)) {
      const conv = makeConversation();
      convId = conv.id;
      setConversations((prev) => [...prev, conv]);
      setActiveId(convId);
    }

    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId
          ? { ...c, title: c.messages.length === 0 ? q.slice(0, 50) : c.title, messages: [...c.messages, { role: "user", text: q }] }
          : c
      )
    );

    setLoading(true);
    try {
      const data = await api.mitre(q);
      updateConversation(convId, (c) => ({
        ...c,
        messages: [...c.messages, { role: "assistant", answer: data.answer, sources: data.sources, model: data.model }],
      }));
    } catch (e) {
      updateConversation(convId, (c) => ({
        ...c,
        messages: [...c.messages, { role: "assistant", answer: `Error: ${e.message}`, sources: [], model: null }],
      }));
    } finally {
      setLoading(false);
    }
  }

  function handleNewChat() {
    const conv = makeConversation();
    setConversations((prev) => [...prev, conv]);
    setActiveId(conv.id);
    setInput("");
  }

  function handleDelete(id) {
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (activeId === id) {
      const remaining = conversations.filter((c) => c.id !== id);
      setActiveId(remaining.length > 0 ? remaining[remaining.length - 1].id : null);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  return (
    <div className="flex h-[calc(100vh-56px)]">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={(id) => { setActiveId(id); setInput(""); }}
        onNew={handleNewChat}
        onDelete={handleDelete}
      />

      <div className="flex-1 flex flex-col min-w-0">
        {messages.length === 0 && !loading && (
          <div className="flex-1 flex flex-col items-center justify-center text-center gap-4 px-4">
            <h1 className="text-2xl font-bold text-white">
              <span className="text-blue-400">MITRE ATT&CK</span> Intelligence
            </h1>
            <p className="text-gray-400 text-sm">Search attack techniques, tactics, and sub-techniques</p>
            <div className="flex flex-wrap gap-2 justify-center mt-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => handleSend(s)}
                  className="text-xs px-3 py-1 rounded-full border border-blue-800 text-blue-400 hover:bg-blue-900/40 transition-colors">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {(messages.length > 0 || loading) && (
          <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4 max-w-4xl w-full mx-auto">
            {messages.map((msg, i) =>
              msg.role === "user"
                ? <UserBubble key={i} text={msg.text} />
                : <AssistantBubble key={i} answer={msg.answer} sources={msg.sources} model={msg.model} />
            )}
            {loading && <AssistantBubble loading />}
            <div ref={bottomRef} />
          </div>
        )}

        {messages.length === 0 && !loading && <div className="flex-1" />}

        <div className="px-4 py-4 max-w-4xl w-full mx-auto">
          {messages.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => handleSend(s)}
                  className="text-xs px-3 py-1 rounded-full border border-blue-800 text-blue-400 hover:bg-blue-900/40 transition-colors">
                  {s}
                </button>
              ))}
            </div>
          )}
          <div className="flex gap-2 items-end bg-gray-800 border border-gray-700 rounded-2xl px-4 py-3 focus-within:border-blue-500 transition-colors">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g. What techniques are used for privilege escalation?"
              rows={1}
              className="flex-1 bg-transparent text-white placeholder-gray-500 text-sm resize-none outline-none max-h-40 leading-relaxed"
              style={{ fieldSizing: "content" }}
            />
            <button onClick={() => handleSend()} disabled={loading || !input.trim()}
              className="flex-shrink-0 px-4 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-xl font-medium text-sm transition-colors">
              {loading ? "..." : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
