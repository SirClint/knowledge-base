import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, friendlyError } from "../api/client";

interface User { id: string; email: string; role: string; is_active: boolean; }

const ROLES = ["reader", "editor", "admin"];

export default function UsersPage() {
  const navigate = useNavigate();
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);

  // Guard: non-admin should not reach this page
  useEffect(() => {
    if (localStorage.getItem("role") !== "admin") {
      navigate("/");
      return;
    }
    api.getMe().then((me: User) => setCurrentUserId(me.id)).catch(() => {});
    load();
  }, []);

  async function load() {
    try {
      const data = await api.listUsers();
      setUsers(data);
    } catch (e: any) {
      setError(friendlyError(e));
    }
  }

  async function changeRole(id: string, role: string) {
    setError(""); setMessage("");
    try {
      await api.changeRole(id, role);
      setMessage("Role updated.");
      load();
    } catch (e: any) {
      setError(friendlyError(e));
    }
  }

  async function resetPassword(id: string, email: string) {
    const pw = window.prompt(`Set new password for ${email} (min 8 chars):`);
    if (!pw) return;
    if (pw.trim().length < 8) { setError("Password must be at least 8 characters."); return; }
    setError(""); setMessage("");
    try {
      await api.resetPassword(id, pw);
      setMessage(`Password reset for ${email}.`);
    } catch (e: any) {
      setError(friendlyError(e));
    }
  }

  async function deleteUser(id: string, email: string) {
    if (!window.confirm(`Delete account for ${email}? This cannot be undone.`)) return;
    setError(""); setMessage("");
    try {
      await api.deleteUser(id);
      setMessage(`Deleted ${email}.`);
      load();
    } catch (e: any) {
      setError(friendlyError(e));
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "40px auto", padding: 24 }}>
      <h2 style={{ marginTop: 0 }}>User Management</h2>
      {error && <div style={{ color: "red", marginBottom: 12 }}>{error}</div>}
      {message && <div style={{ color: "green", marginBottom: 12 }}>{message}</div>}
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
        <thead>
          <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
            <th style={{ padding: "8px 12px" }}>Email</th>
            <th style={{ padding: "8px 12px" }}>Role</th>
            <th style={{ padding: "8px 12px" }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map(u => {
            const isSelf = u.id === currentUserId;
            return (
              <tr key={u.id} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: "8px 12px" }}>{u.email}{isSelf && <span style={{ color: "#888", fontSize: 11, marginLeft: 6 }}>(you)</span>}</td>
                <td style={{ padding: "8px 12px" }}>
                  <select
                    value={u.role}
                    onChange={e => changeRole(u.id, e.target.value)}
                    disabled={isSelf}
                    style={{ fontSize: 13, opacity: isSelf ? 0.5 : 1 }}
                  >
                    {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td style={{ padding: "8px 12px", display: "flex", gap: 8 }}>
                  <button onClick={() => resetPassword(u.id, u.email)} style={{ fontSize: 12 }}>
                    Reset Password
                  </button>
                  <button
                    onClick={() => deleteUser(u.id, u.email)}
                    disabled={isSelf}
                    style={{ fontSize: 12, color: "white", background: isSelf ? "#999" : "#dc2626", border: "none", padding: "3px 8px", cursor: isSelf ? "not-allowed" : "pointer" }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
