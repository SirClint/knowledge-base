import { api } from "../api/client";

interface Doc { id: number; path: string; title: string; last_reviewed: string; }
interface Props { docs: Doc[]; onMarked: (id: number) => void; }

export default function ReviewQueue({ docs, onMarked }: Props) {
  if (docs.length === 0) return <p>No docs need review.</p>;
  return (
    <ul style={{ listStyle: "none", padding: 0 }}>
      {docs.map(d => (
        <li key={d.id} style={{ borderBottom: "1px solid #eee", padding: "12px 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <a href={`/doc/${d.path}`}>{d.title || d.path}</a>
            <div style={{ color: "#888", fontSize: 12 }}>Last reviewed: {d.last_reviewed || "never"}</div>
          </div>
          <button onClick={() => api.markReviewed(d.id).then(() => onMarked(d.id))}>
            Mark reviewed
          </button>
        </li>
      ))}
    </ul>
  );
}
