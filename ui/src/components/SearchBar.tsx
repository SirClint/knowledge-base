import { useState } from "react";

interface Props {
  onSearch: (query: string) => void;
}

export default function SearchBar({ onSearch }: Props) {
  const [query, setQuery] = useState("");
  return (
    <form
      onSubmit={e => { e.preventDefault(); onSearch(query); }}
      style={{ display: "flex", gap: 8, marginBottom: 16 }}
    >
      <input
        value={query}
        onChange={e => setQuery(e.target.value)}
        placeholder="Search docs..."
        style={{ flex: 1, padding: 8 }}
      />
      <button type="submit">Search</button>
    </form>
  );
}
