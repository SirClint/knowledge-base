import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import ReviewQueue from "../components/ReviewQueue";

interface Doc { id: number; path: string; title: string; last_reviewed: string; reason?: string; }

export default function ReviewPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const navigate = useNavigate();

  useEffect(() => { api.reviewQueue().then(setDocs); }, []);

  function handleMarked(id: number) {
    setDocs(d => d.filter(doc => doc.id !== id));
  }

  return (
    <div style={{ maxWidth: 800, margin: "40px auto", padding: 24 }}>
      <button onClick={() => navigate("/")}>← Back</button>
      <h1>Review Queue</h1>
      <ReviewQueue docs={docs} onMarked={handleMarked} />
    </div>
  );
}
