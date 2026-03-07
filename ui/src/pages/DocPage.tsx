import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
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

  useEffect(() => {
    if (!isNew && path) {
      api.getDoc(path).then(setDoc).catch(() => setError("Document not found"));
    }
  }, [path, isNew]);

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

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: 24 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button onClick={() => navigate("/")}>← Back</button>
        {!isNew && !editing && <button onClick={() => setEditing(true)}>Edit</button>}
        {!isNew && editing && <button onClick={save}>Save</button>}
        {!isNew && editing && <button onClick={() => setEditing(false)}>Cancel</button>}
        {!isNew && error && <span style={{ color: "red", marginLeft: 8 }}>{error}</span>}
      </div>

      {isNew ? (
        <div>
          <h2 style={{ marginTop: 0 }}>New Document</h2>
          <p style={{ color: "#888", fontSize: 13, marginBottom: 12 }}>
            Paste or describe your content. AI will determine the title, folder, and whether to create or update an existing document.
          </p>
          <textarea
            value={ingestText}
            onChange={e => setIngestText(e.target.value)}
            placeholder="Paste notes, content, or describe what you want to document..."
            disabled={ingesting}
            style={{
              display: "block", width: "100%", height: 300,
              padding: 8, fontSize: 14, boxSizing: "border-box",
              fontFamily: "monospace", resize: "vertical",
            }}
          />
          {error && <div style={{ color: "red", marginTop: 8 }}>{error}</div>}
          <button
            onClick={ingest}
            disabled={ingesting || !ingestText.trim()}
            style={{ marginTop: 8 }}
          >
            {ingesting ? "Processing with AI..." : "Process with AI"}
          </button>
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
        <DocViewer title={doc.title} body={doc.body} />
      )}
    </div>
  );
}
