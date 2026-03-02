import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";

export default function Register() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [role, setRole] = useState("editor");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    try {
      await api.register(email, password, role);
      navigate("/login");
    } catch (err: any) {
      const detail = err?.detail;
      if (typeof detail === "string") {
        setError(detail);
      } else if (Array.isArray(detail)) {
        setError(detail.map((d: any) => d.msg ?? d).join(", "));
      } else if (detail?.reason) {
        setError(detail.reason);
      } else {
        setError(JSON.stringify(err) ?? "Registration failed");
      }
    }
  }

  return (
    <div style={{ maxWidth: 400, margin: "100px auto", padding: 24 }}>
      <h1>Knowledge Base</h1>
      <form onSubmit={submit}>
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          required
          style={{ display: "block", width: "100%", marginBottom: 8, padding: 8, boxSizing: "border-box" }}
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          required
          style={{ display: "block", width: "100%", marginBottom: 8, padding: 8, boxSizing: "border-box" }}
        />
        <input
          type="password"
          placeholder="Confirm password"
          value={confirm}
          onChange={e => setConfirm(e.target.value)}
          required
          style={{ display: "block", width: "100%", marginBottom: 8, padding: 8, boxSizing: "border-box" }}
        />
        <select
          value={role}
          onChange={e => setRole(e.target.value)}
          style={{ display: "block", width: "100%", marginBottom: 8, padding: 8, boxSizing: "border-box" }}
        >
          <option value="reader">Reader — view and search</option>
          <option value="editor">Editor — create and edit docs</option>
          <option value="admin">Admin — full access</option>
        </select>
        {error && <p style={{ color: "red" }}>{error}</p>}
        <button type="submit" style={{ width: "100%", padding: 8 }}>Register</button>
      </form>
      <p style={{ textAlign: "center", marginTop: 16 }}>
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </div>
  );
}
