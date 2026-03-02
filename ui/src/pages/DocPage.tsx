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
  const [editing, setEditing] = useState(isNew);

  useEffect(() => {
    if (!isNew && path) api.getDoc(path).then(setDoc);
  }, [path, isNew]);

  async function save() {
    if (isNew) {
      await api.createDoc({ title: doc.title, path: doc.path, body: doc.body, tags: [] });
      navigate(`/doc/${doc.path}`);
    } else {
      await api.updateDoc(path!, { title: doc.title, body: doc.body });
      setEditing(false);
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: 24 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button onClick={() => navigate("/")}>← Back</button>
        {!editing && <button onClick={() => setEditing(true)}>Edit</button>}
        {editing && <button onClick={save}>Save</button>}
        {editing && !isNew && <button onClick={() => setEditing(false)}>Cancel</button>}
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
            <input
              value={doc.path}
              onChange={e => setDoc(d => ({ ...d, path: e.target.value }))}
              placeholder="Path (e.g. team/processes/deploy.md)"
              style={{ display: "block", width: "100%", marginBottom: 8, padding: 8, boxSizing: "border-box" }}
            />
          )}
          <Editor value={doc.body} onChange={body => setDoc(d => ({ ...d, body }))} />
        </>
      ) : (
        <DocViewer title={doc.title} body={doc.body} />
      )}
    </div>
  );
}
