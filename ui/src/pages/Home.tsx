import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import SearchBar from "../components/SearchBar";

interface DocResult { id: number; path: string; title: string; }

export default function Home() {
  const [results, setResults] = useState<DocResult[]>([]);
  const navigate = useNavigate();

  async function handleSearch(q: string) {
    if (!q.trim()) return;
    const data = await api.search(q);
    setResults(data);
  }

  return (
    <div style={{ maxWidth: 800, margin: "40px auto", padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Knowledge Base</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => navigate("/doc/new")}>+ New Doc</button>
          <button onClick={() => navigate("/review")}>Review Queue</button>
          <button onClick={() => { localStorage.removeItem("token"); navigate("/login"); }}>Log out</button>
        </div>
      </div>
      <SearchBar onSearch={handleSearch} />
      <ul style={{ listStyle: "none", padding: 0 }}>
        {results.map(r => (
          <li key={r.id} style={{ borderBottom: "1px solid #eee", padding: "8px 0" }}>
            <a href={`/doc/${r.path}`} style={{ textDecoration: "none" }}>{r.title || r.path}</a>
            <span style={{ color: "#888", fontSize: 12, marginLeft: 8 }}>{r.path}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
