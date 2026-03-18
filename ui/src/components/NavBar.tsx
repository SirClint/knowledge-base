import { useNavigate, Link } from "react-router-dom";

export default function NavBar() {
  const navigate = useNavigate();
  const role = localStorage.getItem("role");

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    navigate("/login");
  }

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
        {role === "admin" && (
          <Link to="/admin" style={{ textDecoration: "none", color: "#555" }}>Admin</Link>
        )}
        <button onClick={logout} style={{ fontSize: 12, padding: "2px 8px" }}>Log out</button>
      </div>
    </div>
  );
}
