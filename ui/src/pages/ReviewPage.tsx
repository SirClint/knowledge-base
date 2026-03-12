import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import ReviewQueue from "../components/ReviewQueue";

interface Doc { id: number; path: string; title: string; last_reviewed: string; reason?: string; }

export default function ReviewPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  useEffect(() => { api.reviewQueue().then(setDocs); }, []);

  function handleMarked(id: number) {
    setDocs(d => d.filter(doc => doc.id !== id));
  }

  return (
    <div style={{ maxWidth: 800, margin: "40px auto", padding: 24 }}>
      <Link to="/" style={{ textDecoration: "none", color: "inherit" }}>← Back</Link>
      <h1>Review Queue</h1>
      <ReviewQueue docs={docs} onMarked={handleMarked} />
    </div>
  );
}
