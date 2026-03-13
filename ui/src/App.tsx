import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Home from "./pages/Home";
import DocPage from "./pages/DocPage";
import ReviewPage from "./pages/ReviewPage";
import UsersPage from "./pages/UsersPage";
import Layout from "./components/Layout";

const isTest = window.location.port === "8081";

function isTokenValid(token: string | null): boolean {
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return typeof payload.exp === "number" && payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem("token");
  if (!isTokenValid(token)) {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("email");
    return <Navigate to="/login" />;
  }
  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <BrowserRouter basename="/kms">
      {isTest && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, zIndex: 9999,
          background: "#f59e0b", color: "#000", textAlign: "center",
          fontWeight: "bold", fontSize: 13, padding: "4px 0",
          letterSpacing: "0.05em",
        }}>
          ⚠ TEST ENVIRONMENT
        </div>
      )}
      <div style={isTest ? { paddingTop: 26 } : undefined}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/" element={<PrivateRoute><Home /></PrivateRoute>} />
          <Route path="/doc/*" element={<PrivateRoute><DocPage /></PrivateRoute>} />
          <Route path="/review" element={<PrivateRoute><ReviewPage /></PrivateRoute>} />
          <Route path="/users" element={<PrivateRoute><UsersPage /></PrivateRoute>} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
