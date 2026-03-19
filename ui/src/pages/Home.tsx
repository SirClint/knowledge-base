import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";
import SearchBar from "../components/SearchBar";

interface DocResult { id: number; path: string; title: string; }

/** Derive a nested folder tree from known folder paths and flat doc paths.
 *  Known folders are always shown even when empty.
 *  e.g. ["personal/a.md", "team/processes/b.md"]
 *  → { personal: {}, team: { processes: {} } }
 */
function buildFolderTree(docs: DocResult[], knownFolders: string[]): Record<string, Record<string, object>> {
  const tree: Record<string, Record<string, object>> = {};

  // Seed with known folders so they always appear
  for (const folder of knownFolders) {
    const parts = folder.split("/");
    const [top, sub] = parts;
    if (!tree[top]) tree[top] = {};
    if (sub) (tree[top] as Record<string, object>)[sub] = {};
  }

  // Add any additional folders found in docs
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
  const [knownFolders, setKnownFolders] = useState<string[]>([]);
  const [results, setResults] = useState<DocResult[]>([]);
  const [activeFolder, setActiveFolder] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [showAbout, setShowAbout] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.listDocs()
      .then((docs: DocResult[]) => setAllDocs(docs))
      .catch(() => {});
    api.getFolders()
      .then((folders: string[]) => {
        setKnownFolders(folders);
        // Default-expand top-level folders
        const tops = [...new Set(folders.map(f => f.split("/")[0]))];
        setExpanded(prev => Object.fromEntries(tops.map(t => [t, prev[t] ?? true])));
      })
      .catch(() => {});
  }, []);

  const folderTree = buildFolderTree(allDocs, knownFolders);

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
          <button onClick={() => navigate("/doc/new")}>+ Ingest</button>
          <button onClick={() => navigate("/review")}>Review Queue</button>
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
          <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid #ddd" }}>
            <span
              onClick={() => setShowAbout(true)}
              style={{ fontSize: 12, color: "#888", cursor: "pointer" }}
            >
              About
            </span>
          </div>
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
      {showAbout && (
        <div
          onClick={() => setShowAbout(false)}
          style={{
            position: "fixed", inset: 0,
            background: "rgba(0,0,0,0.4)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: "white", borderRadius: 6, padding: 24,
              maxWidth: 400, width: "90%", position: "relative",
            }}
          >
            <button
              onClick={() => setShowAbout(false)}
              style={{
                position: "absolute", top: 12, right: 12,
                border: "none", background: "none", cursor: "pointer", fontSize: 16,
              }}
            >
              ✕
            </button>
            <h2 style={{ marginTop: 0, marginBottom: 16 }}>Knowledge Base</h2>
            <p style={{ margin: "0 0 8px" }}><strong>Version:</strong> 0.0.1</p>
            <p style={{ margin: "0 0 8px" }}>
              <strong>GitHub:</strong>{" "}
              <a href="https://github.com/SirClint/knowledge-base" target="_blank" rel="noreferrer">
                github.com/SirClint/knowledge-base
              </a>
            </p>
            <div style={{ marginTop: 12 }}>
              <strong>Tech Stack</strong>
              <ul style={{ margin: "8px 0 0", paddingLeft: 20, fontSize: 13 }}>
                <li><strong>Frontend:</strong> React 18, TypeScript, Vite, CodeMirror 6</li>
                <li><strong>Backend:</strong> FastAPI, Python, SQLite, ChromaDB, Ollama</li>
                <li><strong>Infra:</strong> Docker, Caddy, Nginx</li>
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
