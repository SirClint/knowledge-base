import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";
import SearchBar from "../components/SearchBar";

interface DocResult { id: number; path: string; title: string; }

/** Derive a nested folder tree from flat doc paths.
 *  e.g. ["personal/a.md", "team/processes/b.md"]
 *  → { personal: {}, team: { processes: {} } }
 */
function buildFolderTree(docs: DocResult[]): Record<string, Record<string, object>> {
  const tree: Record<string, Record<string, object>> = {};
  for (const doc of docs) {
    const parts = doc.path.split("/");
    if (parts.length < 2) continue;
    const [top, ...rest] = parts;
    if (!tree[top]) tree[top] = {};
    if (rest.length >= 2) {
      const sub = rest[0];
      if (!(tree[top] as Record<string, object>)[sub]) (tree[top] as Record<string, object>)[sub] = {};
    }
  }
  return tree;
}

export default function Home() {
  const [allDocs, setAllDocs] = useState<DocResult[]>([]);
  const [results, setResults] = useState<DocResult[]>([]);
  const [activeFolder, setActiveFolder] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api.listDocs().then((docs: DocResult[]) => setAllDocs(docs));
  }, []);

  const folderTree = buildFolderTree(allDocs);

  function handleFolderClick(folderPath: string) {
    setActiveFolder(folderPath);
    setSearchQuery("");
    setResults(allDocs.filter(d => d.path.startsWith(folderPath + "/")));
  }

  function toggleExpand(folder: string) {
    setExpanded(prev => ({ ...prev, [folder]: !prev[folder] }));
  }

  async function handleSearch(q: string) {
    if (!q.trim()) return;
    setActiveFolder(null);
    const data = await api.search(q);
    setResults(data);
  }

  const activeFolderStyle = { fontWeight: "bold" as const, color: "#0055cc" };
  const folderItemStyle = { cursor: "pointer", padding: "4px 0", userSelect: "none" as const };

  return (
    <div style={{ maxWidth: 1100, margin: "40px auto", padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Knowledge Base</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => navigate("/doc/new")}>+ New Doc</button>
          <button onClick={() => navigate("/review")}>Review Queue</button>
          <button onClick={() => { localStorage.removeItem("token"); navigate("/login"); }}>Log out</button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
        {/* Sidebar */}
        <div style={{ width: 220, flexShrink: 0, borderRight: "1px solid #ddd", paddingRight: 16 }}>
          <div style={{ fontSize: 12, fontWeight: "bold", color: "#888", marginBottom: 8, textTransform: "uppercase" as const }}>
            Folders
          </div>
          {Object.keys(folderTree).sort().map(top => {
            const subFolders = Object.keys(folderTree[top] as Record<string, object>).sort();
            const isTopActive = activeFolder === top;
            const isExpanded = expanded[top];
            return (
              <div key={top}>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  {subFolders.length > 0
                    ? <span style={{ fontSize: 10, cursor: "pointer", width: 12 }} onClick={() => toggleExpand(top)}>
                        {isExpanded ? "▼" : "▶"}
                      </span>
                    : <span style={{ width: 12 }} />
                  }
                  <span
                    style={{ ...folderItemStyle, ...(isTopActive ? activeFolderStyle : {}) }}
                    onClick={() => handleFolderClick(top)}
                  >
                    {top}
                  </span>
                </div>
                {isExpanded && subFolders.map(sub => {
                  const subPath = `${top}/${sub}`;
                  return (
                    <div
                      key={sub}
                      style={{ ...folderItemStyle, paddingLeft: 24, ...(activeFolder === subPath ? activeFolderStyle : {}) }}
                      onClick={() => handleFolderClick(subPath)}
                    >
                      {sub}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>

        {/* Main content */}
        <div style={{ flex: 1 }}>
          <SearchBar onSearch={handleSearch} value={searchQuery} onChange={setSearchQuery} />
          {activeFolder && (
            <div style={{ color: "#888", fontSize: 13, marginBottom: 8 }}>
              Browsing: <strong>{activeFolder}</strong>
              <span
                style={{ marginLeft: 8, cursor: "pointer", color: "#cc0000" }}
                onClick={() => { setActiveFolder(null); setResults([]); }}
              >
                ✕
              </span>
            </div>
          )}
          <ul style={{ listStyle: "none", padding: 0 }}>
            {results.map(r => (
              <li key={r.id} style={{ borderBottom: "1px solid #eee", padding: "8px 0" }}>
                <Link to={`/doc/${r.path}`} style={{ textDecoration: "none" }}>{r.title || r.path}</Link>
                <span style={{ color: "#888", fontSize: 12, marginLeft: 8 }}>{r.path}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
