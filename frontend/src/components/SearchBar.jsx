import { useState } from "react";

export default function SearchBar({ onSearch, loading, placeholder }) {
  const [value, setValue] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    if (value.trim()) onSearch(value.trim());
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 w-full">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder ?? "Ask a threat intelligence question..."}
        className="flex-1 bg-gray-800 border border-gray-600 rounded-lg px-4 py-3
                   text-white placeholder-gray-500 focus:outline-none focus:border-blue-500
                   text-sm"
      />
      <button
        type="submit"
        disabled={loading || !value.trim()}
        className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700
                   disabled:text-gray-500 text-white rounded-lg font-medium text-sm
                   transition-colors"
      >
        {loading ? "Searching..." : "Search"}
      </button>
    </form>
  );
}
