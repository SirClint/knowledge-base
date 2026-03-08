import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";

export default function NavBar() {
  const [aiStatus, setAiStatus] = useState<"online" | "offline" | "checking">("checking");
  const navigate = useNavigate();
  const role = localStorage.getItem("role");
  const BASE = import.meta.env.VITE_API_URL ?? "/kms/api";

  async function checkAi() {
    try {
      const r = await fetch(`${BASE}/health/ai`);
      const data = await r.json();
      setAiStatus(data.ai === "online" ? "online" : "offline");
    } catch {
      setAiStatus("offline");
    }
  }

  useEffect(() => {
    checkAi();
    const interval = setInterval(checkAi, 30000);
    const onFocus = () => checkAi();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    navigate("/login");
  }

  const dotColor = aiStatus === "online" ? "#22c55e" : aiStatus === "offline" ? "#ef4444" : "#999";
  const dotLabel = aiStatus === "checking" ? "AI: checking..." : `AI: ${aiStatus}`;

  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "8px 24px", background: "#f8f8f8", borderBottom: "1px solid #ddd",
      fontSize: 13,
    }}>
      <Link to="/" style={{ fontWeight: "bold", textDecoration: "none", color: "#333" }}>
        Knowledge Base
      </Link>
      <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
        <span>
          <span style={{
            display: "inline-block", width: 8, height: 8, borderRadius: "50%",
            background: dotColor, marginRight: 5,
          }} />
          {dotLabel}
        </span>
        {role === "admin" && (
          <Link to="/users" style={{ textDecoration: "none", color: "#555" }}>Users</Link>
        )}
        <button onClick={logout} style={{ fontSize: 12, padding: "2px 8px" }}>Log out</button>
      </div>
    </div>
  );
}
