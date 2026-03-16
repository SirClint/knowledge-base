import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, BASE, friendlyError } from "../api/client";
import DocViewer from "../components/DocViewer";
import Editor from "../components/Editor";

interface Doc { title: string; body: string; path: string; }

export default function DocPage() {
  const { "*": path } = useParams();
  const navigate = useNavigate();
  const isNew = path === "new";
  const [doc, setDoc] = useState<Doc>({ title: "", body: "", path: "" });
  const [editSnapshot, setEditSnapshot] = useState<Doc | null>(null);
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
  const [comments, setComments] = useState<{id: number; body: string; author_email: string; created_at: string}[]>([]);
  const [newComment, setNewComment] = useState("");
  const [commentError, setCommentError] = useState("");
  const [ingestReason, setIngestReason] = useState<string>(() => {
    const r = sessionStorage.getItem("ingestReason") ?? "";
    sessionStorage.removeItem("ingestReason");
    return r;
  });

  const currentEmail = localStorage.getItem("email") ?? "";
  const currentRole = localStorage.getItem("role") ?? "reader";

  async function loadComments() {
    if (!path || isNew) return;
    try {
      const data = await api.listComments(path);
      setComments(data);
    } catch {
      // non-critical
    }
  }

  useEffect(() => {
    if (!isNew && path) {
      api.getDoc(path).then(setDoc).catch(() => setError("Document not found — it may have been deleted or moved. If unexpected, contact IT support."));
      // Inline to avoid stale-closure dep warning; loadComments() still used by handlers
      api.listComments(path).then(setComments).catch(() => {});
    }
  }, [path, isNew]);

  useEffect(() => {
    if (!isNew) return;
    fetch(`${BASE}/health/ai`).then(r => r.json()).then(d => setAiOnline(d.ai === "online"));
    api.getFolders().then(setFolders);
  }, [isNew]);

  async function deleteDoc() {
    if (!window.confirm(`Delete "${doc.title || path}"? This cannot be undone.`)) return;
    setError("");
    try {
      await api.deleteDoc(path!);
      navigate("/");
    } catch (e: any) {
      setError(friendlyError(e));
    }
  }

  async function save() {
    setError("");
    try {
      await api.updateDoc(path!, { title: doc.title, body: doc.body });
      setEditing(false);
    } catch (e: any) {
      setError(friendlyError(e));
    }
  }

  async function ingest() {
    if (!ingestText.trim()) return;
    setIngesting(true);
    setError("");
    try {
      const result = await api.ingest(ingestText);
      sessionStorage.setItem("ingestReason", result.reason ?? "");
      navigate(`/doc/${result.path}`);
    } catch (e: any) {
      setError(friendlyError(e));
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
      setError(friendlyError(e));
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
      setError(friendlyError(e));
    }
  }

  async function submitComment() {
    if (!newComment.trim()) return;
    setCommentError("");
    try {
      await api.addComment(path!, newComment);
      setNewComment("");
      loadComments();
    } catch (e: any) {
      setCommentError(friendlyError(e));
    }
  }

  async function removeComment(id: number) {
    setCommentError("");
    try {
      await api.deleteComment(id);
      loadComments();
    } catch (e: any) {
      setCommentError(friendlyError(e));
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: 24 }}>
      {ingestReason && (
        <div style={{
          background: "#e8f4fd",
          border: "1px solid #b3d9f7",
          borderRadius: 4,
          padding: "10px 14px",
          marginBottom: 16,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          fontSize: 14,
        }}>
          <span>🤖 {ingestReason}</span>
          <button
            onClick={() => setIngestReason("")}
            style={{ background: "none", border: "none", cursor: "pointer", marginLeft: 12, fontSize: 16, lineHeight: 1 }}
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button onClick={() => navigate("/")}>← Back</button>
        {!isNew && !editing && currentRole !== "reader" && <button onClick={() => { setEditSnapshot({ ...doc }); setEditing(true); }}>Edit</button>}
        {!isNew && !editing && <button onClick={() => { const opening = !showHistory; setShowHistory(opening); if (opening) loadVersions(); }}>History</button>}
        {!isNew && !editing && currentRole === "admin" && (
          <button onClick={deleteDoc} style={{ color: "white", background: "#dc2626", border: "none", padding: "4px 10px", cursor: "pointer", borderRadius: 3 }}>
            Delete
          </button>
        )}
        {!isNew && editing && <button onClick={save}>Save</button>}
        {!isNew && editing && <button onClick={() => { if (editSnapshot) setDoc(editSnapshot); setEditSnapshot(null); setEditing(false); }}>Cancel</button>}
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
            <div style={{ position: "relative" }}>
              <p style={{ color: "#888", fontSize: 13, marginBottom: 12 }}>
                Paste or describe your content. AI will determine the title, folder, and whether to create or update an existing document.
                {" "}<span style={{ color: "#aaa" }}>First use after 5+ minutes of inactivity may take longer while the model reloads.</span>
              </p>
              {aiOnline === false && (
                <div style={{ color: "#b45309", background: "#fef3c7", padding: "8px 12px", borderRadius: 4, marginBottom: 12, fontSize: 13 }}>
                  AI is currently offline. Use the Manual tab to create a document without AI.
                </div>
              )}
              <div style={{ position: "relative" }}>
                <textarea
                  value={ingestText}
                  onChange={e => setIngestText(e.target.value)}
                  placeholder="Paste notes, content, or describe what you want to document..."
                  disabled={ingesting || aiOnline === false}
                  style={{
                    display: "block", width: "100%", height: 300,
                    padding: 8, fontSize: 14, boxSizing: "border-box",
                    fontFamily: "monospace", resize: "vertical",
                    opacity: ingesting || aiOnline === false ? 0.4 : 1,
                  }}
                />
                {ingesting && (
                  <div style={{
                    position: "absolute", inset: 0,
                    display: "flex", flexDirection: "column",
                    alignItems: "center", justifyContent: "center", gap: 12,
                    background: "rgba(255,255,255,0.7)", borderRadius: 4,
                  }}>
                    <div style={{
                      width: 32, height: 32, border: "3px solid #ddd",
                      borderTopColor: "#f59e0b", borderRadius: "50%",
                      animation: "spin 0.8s linear infinite",
                    }} />
                    <div style={{ fontWeight: "bold", fontSize: 14 }}>AI is processing...</div>
                    <div style={{ fontSize: 12, color: "#666" }}>This may take 10–30 seconds</div>
                  </div>
                )}
              </div>
              {error && <div style={{ color: "red", marginTop: 8 }}>{error}</div>}
              <button
                onClick={ingest}
                disabled={ingesting || !ingestText.trim() || aiOnline === false}
                title={aiOnline === false ? "AI is currently offline" : undefined}
                style={{ marginTop: 8, opacity: aiOnline === false ? 0.5 : 1, cursor: ingesting || aiOnline === false ? "not-allowed" : "pointer" }}
              >
                {ingesting ? "Processing..." : "Process with AI"}
              </button>
              <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
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
          <div style={{ marginTop: 32, borderTop: "1px solid #eee", paddingTop: 24 }}>
            <strong style={{ fontSize: 15 }}>
              Comments {comments.length > 0 && `(${comments.length})`}
            </strong>
            <div style={{ marginTop: 12 }}>
              {comments.map(c => (
                <div key={c.id} style={{ padding: "10px 0", borderBottom: "1px solid #f0f0f0", fontSize: 14 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <span style={{ fontWeight: "bold", fontSize: 12, color: "#555" }}>{c.author_email}</span>
                      <span style={{ color: "#aaa", fontSize: 11, marginLeft: 8 }}>
                        {new Date(c.created_at).toLocaleString()}
                      </span>
                    </div>
                    {(c.author_email === currentEmail || currentRole === "editor" || currentRole === "admin") && (
                      <button
                        onClick={() => removeComment(c.id)}
                        style={{ fontSize: 11, color: "#dc2626", background: "none", border: "none", cursor: "pointer" }}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                  <div style={{ marginTop: 4 }}>{c.body}</div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 16 }}>
              <textarea
                value={newComment}
                onChange={e => setNewComment(e.target.value)}
                placeholder="Add a comment..."
                style={{
                  display: "block", width: "100%", height: 80, padding: 8,
                  fontSize: 13, boxSizing: "border-box", resize: "vertical"
                }}
              />
              {commentError && <div style={{ color: "red", fontSize: 12, marginTop: 4 }}>{commentError}</div>}
              <button
                onClick={submitComment}
                disabled={!newComment.trim()}
                style={{ marginTop: 6, fontSize: 13 }}
              >
                Add Comment
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
