import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, BASE } from "../api/client";
import DocViewer from "../components/DocViewer";
import Editor from "../components/Editor";

interface Doc { title: string; body: string; path: string; }

export default function DocPage() {
  const { "*": path } = useParams();
  const navigate = useNavigate();
  const isNew = path === "new";
  const [doc, setDoc] = useState<Doc>({ title: "", body: "", path: "" });
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");
  // AI ingestion state (only used when isNew)
  const [ingestText, setIngestText] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [tab, setTab] = useState<"ai" | "manual">("ai");
  const [folders, setFolders] = useState<string[]>([]);
  const [manualTitle, setManualTitle] = useState("");
  const [manualFolder, setManualFolder] = useState("");
  const [aiOnline, setAiOnline] = useState<boolean | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [versions, setVersions] = useState<{id: number; saved_by: string; saved_at: string}[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(false);

  useEffect(() => {
    if (!isNew && path) {
      api.getDoc(path).then(setDoc).catch(() => setError("Document not found"));
    }
  }, [path, isNew]);

  useEffect(() => {
    if (!isNew) return;
    fetch(`${BASE}/health/ai`).then(r => r.json()).then(d => setAiOnline(d.ai === "online"));
    api.getFolders().then(setFolders);
  }, [isNew]);

  async function save() {
    setError("");
    try {
      await api.updateDoc(path!, { title: doc.title, body: doc.body });
      setEditing(false);
    } catch (e: any) {
      if (e.message?.includes("403")) {
        setError("Permission denied. Your account needs the editor or admin role to save documents.");
      } else {
        setError(e.message ?? "Save failed");
      }
    }
  }

  async function ingest() {
    if (!ingestText.trim()) return;
    setIngesting(true);
    setError("");
    try {
      const result = await api.ingest(ingestText);
      navigate(`/doc/${result.path}`);
    } catch (e: any) {
      setError(e.message ?? "Processing failed");
      setIngesting(false);
    }
  }

  async function loadVersions() {
    if (!path || isNew) return;
    setLoadingVersions(true);
    try {
      const data = await api.listVersions(path);
      setVersions(data);
    } catch {
      // non-critical — history panel stays empty
    } finally {
      setLoadingVersions(false);
    }
  }

  async function restoreVersion(versionId: number) {
    if (!window.confirm("Restore this version? The current content will be saved as a new version first.")) return;
    setError("");
    try {
      await api.restoreVersion(path!, versionId);
      const updated = await api.getDoc(path!);
      setDoc(updated);
      setShowHistory(false);
      setVersions([]);
    } catch (e: any) {
      setError(e.message ?? "Restore failed");
    }
  }

  async function manualCreate() {
    if (!manualTitle.trim() || !manualFolder) return;
    setError("");
    const slug = manualTitle.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    const path = `${manualFolder}/${slug}.md`;
    try {
      await api.createDoc({ title: manualTitle.trim(), body: "", path, tags: [] });
      navigate(`/doc/${path}`);
    } catch (e: any) {
      setError(e.message ?? "Create failed");
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: 24 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button onClick={() => navigate("/")}>← Back</button>
        {!isNew && !editing && <button onClick={() => setEditing(true)}>Edit</button>}
        {!isNew && !editing && <button onClick={() => { setShowHistory(h => !h); if (!showHistory) loadVersions(); }}>History</button>}
        {!isNew && editing && <button onClick={save}>Save</button>}
        {!isNew && editing && <button onClick={() => setEditing(false)}>Cancel</button>}
        {!isNew && error && <span style={{ color: "red", marginLeft: 8 }}>{error}</span>}
      </div>

      {isNew ? (
        <div>
          <h2 style={{ marginTop: 0 }}>New Document</h2>
          {/* Tab bar */}
          <div style={{ display: "flex", gap: 0, marginBottom: 16, borderBottom: "1px solid #ddd" }}>
            <button
              onClick={() => setTab("ai")}
              style={{
                padding: "6px 16px", border: "none", borderBottom: tab === "ai" ? "2px solid #333" : "2px solid transparent",
                background: "none", cursor: "pointer", fontWeight: tab === "ai" ? "bold" : "normal",
              }}
            >
              AI Ingestion
            </button>
            <button
              onClick={() => setTab("manual")}
              style={{
                padding: "6px 16px", border: "none", borderBottom: tab === "manual" ? "2px solid #333" : "2px solid transparent",
                background: "none", cursor: "pointer", fontWeight: tab === "manual" ? "bold" : "normal",
              }}
            >
              Manual
            </button>
          </div>

          {tab === "ai" ? (
            <div>
              <p style={{ color: "#888", fontSize: 13, marginBottom: 12 }}>
                Paste or describe your content. AI will determine the title, folder, and whether to create or update an existing document.
              </p>
              {aiOnline === false && (
                <div style={{ color: "#b45309", background: "#fef3c7", padding: "8px 12px", borderRadius: 4, marginBottom: 12, fontSize: 13 }}>
                  AI is currently offline. Use the Manual tab to create a document without AI.
                </div>
              )}
              <textarea
                value={ingestText}
                onChange={e => setIngestText(e.target.value)}
                placeholder="Paste notes, content, or describe what you want to document..."
                disabled={ingesting || aiOnline === false}
                style={{
                  display: "block", width: "100%", height: 300,
                  padding: 8, fontSize: 14, boxSizing: "border-box",
                  fontFamily: "monospace", resize: "vertical",
                  opacity: aiOnline === false ? 0.5 : 1,
                }}
              />
              {error && <div style={{ color: "red", marginTop: 8 }}>{error}</div>}
              <button
                onClick={ingest}
                disabled={ingesting || !ingestText.trim() || aiOnline === false}
                title={aiOnline === false ? "AI is currently offline" : undefined}
                style={{ marginTop: 8, opacity: aiOnline === false ? 0.5 : 1, cursor: aiOnline === false ? "not-allowed" : "pointer" }}
              >
                {ingesting ? "Processing with AI..." : "Process with AI"}
              </button>
            </div>
          ) : (
            <div>
              <p style={{ color: "#888", fontSize: 13, marginBottom: 12 }}>
                Enter a title and choose a folder. The document will be created empty and ready to edit.
              </p>
              <input
                value={manualTitle}
                onChange={e => setManualTitle(e.target.value)}
                placeholder="Document title"
                style={{ display: "block", width: "100%", fontSize: 18, marginBottom: 12, padding: 8, boxSizing: "border-box" }}
              />
              <select
                value={manualFolder}
                onChange={e => setManualFolder(e.target.value)}
                style={{ display: "block", width: "100%", padding: 8, fontSize: 14, marginBottom: 12, boxSizing: "border-box" }}
              >
                <option value="">— Select a folder —</option>
                {folders.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
              {error && <div style={{ color: "red", marginBottom: 8 }}>{error}</div>}
              <button
                onClick={manualCreate}
                disabled={!manualTitle.trim() || !manualFolder}
              >
                Create Document
              </button>
            </div>
          )}
        </div>
      ) : editing ? (
        <>
          <input
            value={doc.title}
            onChange={e => setDoc(d => ({ ...d, title: e.target.value }))}
            placeholder="Title"
            style={{ display: "block", width: "100%", fontSize: 24, marginBottom: 8, padding: 8, boxSizing: "border-box" }}
          />
          <Editor value={doc.body} onChange={body => setDoc(d => ({ ...d, body }))} />
        </>
      ) : (
        <>
          <DocViewer title={doc.title} body={doc.body} />
          {showHistory && (
            <div style={{
              marginTop: 24, padding: 16, background: "#f8f8f8",
              borderRadius: 4, border: "1px solid #ddd"
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <strong>Version History</strong>
                <button onClick={() => setShowHistory(false)} style={{ fontSize: 11 }}>Close</button>
              </div>
              {loadingVersions && <div style={{ color: "#888", fontSize: 13 }}>Loading...</div>}
              {!loadingVersions && versions.length === 0 && (
                <div style={{ color: "#888", fontSize: 13 }}>No saved versions yet. Versions are created each time you save.</div>
              )}
              {versions.map(v => (
                <div key={v.id} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "6px 0", borderBottom: "1px solid #eee", fontSize: 13
                }}>
                  <span>
                    <span style={{ color: "#555" }}>{new Date(v.saved_at).toLocaleString()}</span>
                    <span style={{ color: "#888", marginLeft: 8 }}>by {v.saved_by || "unknown"}</span>
                  </span>
                  <button onClick={() => restoreVersion(v.id)} style={{ fontSize: 11 }}>Restore</button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
