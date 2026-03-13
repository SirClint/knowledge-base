import { useState } from "react";
import { Link } from "react-router-dom";
import { api, friendlyError } from "../api/client";

interface Doc { id: number; path: string; title: string; last_reviewed: string; reason?: string; }
interface Props { docs: Doc[]; onMarked: (id: number) => void; }

export default function ReviewQueue({ docs, onMarked }: Props) {
  const [error, setError] = useState("");
  if (docs.length === 0) return <p>No docs need review.</p>;
  return (
    <>
      {error && <div style={{ color: "red", marginBottom: 12, fontSize: 14 }}>{error}</div>}
      <ul style={{ listStyle: "none", padding: 0 }}>
        {docs.map(d => (
          <li key={d.id} style={{ borderBottom: "1px solid #eee", padding: "12px 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <Link to={`/doc/${d.path}`} style={{ textDecoration: "none" }}>{d.title || d.path}</Link>
              <div style={{ color: "#888", fontSize: 12 }}>
                {d.reason || `Last reviewed: ${d.last_reviewed || "never"}`}
              </div>
            </div>
            <button onClick={() =>
              api.markReviewed(d.id)
                .then(() => onMarked(d.id))
                .catch(e => setError(friendlyError(e)))
            }>
              Mark reviewed
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
