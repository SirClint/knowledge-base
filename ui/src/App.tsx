import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Home from "./pages/Home";
import DocPage from "./pages/DocPage";
import ReviewPage from "./pages/ReviewPage";
import UsersPage from "./pages/UsersPage";
import Layout from "./components/Layout";

const isTest = window.location.port === "8081";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  return localStorage.getItem("token")
    ? <Layout>{children}</Layout>
    : <Navigate to="/login" />;
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
