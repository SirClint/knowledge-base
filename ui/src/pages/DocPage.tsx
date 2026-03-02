import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import DocViewer from "../components/DocViewer";
import Editor from "../components/Editor";

interface Doc { title: string; body: string; path: string; }

const CATEGORIES = [
  { value: "team/processes", label: "Processes" },
  { value: "team/architecture", label: "Architecture" },
  { value: "team/projects", label: "Projects" },
  { value: "personal", label: "Personal" },
];

function titleToFilename(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") + ".md";
}

export default function DocPage() {
  const { "*": path } = useParams();
  const navigate = useNavigate();
  const isNew = path === "new";
  const [doc, setDoc] = useState<Doc>({ title: "", body: "", path: "" });
  const [category, setCategory] = useState(CATEGORIES[0].value);
  const [editing, setEditing] = useState(isNew);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isNew && path) {
      api.getDoc(path).then(setDoc).catch(() => setError("Document not found"));
    }
  }, [path, isNew]);

  async function save() {
    setError("");
    try {
      if (isNew) {
        const fullPath = `${category}/${titleToFilename(doc.title)}`;
        await api.createDoc({ title: doc.title, path: fullPath, body: doc.body, tags: [] });
        navigate(`/doc/${fullPath}`);
      } else {
        await api.updateDoc(path!, { title: doc.title, body: doc.body });
        setEditing(false);
      }
    } catch (e: any) {
      if (e.message?.includes("403")) {
        setError("Permission denied. Your account needs the editor or admin role to save documents.");
      } else {
        setError(e.message ?? "Save failed");
      }
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: 24 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button onClick={() => navigate("/")}>← Back</button>
        {!editing && <button onClick={() => setEditing(true)}>Edit</button>}
        {editing && <button onClick={save}>Save</button>}
        {editing && !isNew && <button onClick={() => setEditing(false)}>Cancel</button>}
        {error && <span style={{ color: "red", marginLeft: 8 }}>{error}</span>}
      </div>
      {editing ? (
        <>
          <input
            value={doc.title}
            onChange={e => setDoc(d => ({ ...d, title: e.target.value }))}
            placeholder="Title"
            style={{ display: "block", width: "100%", fontSize: 24, marginBottom: 8, padding: 8, boxSizing: "border-box" }}
          />
          {isNew && (
            <select
              value={category}
              onChange={e => setCategory(e.target.value)}
              style={{ display: "block", width: "100%", marginBottom: 8, padding: 8, boxSizing: "border-box" }}
            >
              {CATEGORIES.map(c => (
                <option key={c.value} value={c.value}>{c.label} ({c.value}/)</option>
              ))}
            </select>
          )}
          <Editor value={doc.body} onChange={body => setDoc(d => ({ ...d, body }))} />
        </>
      ) : (
        <DocViewer title={doc.title} body={doc.body} />
      )}
    </div>
  );
}
