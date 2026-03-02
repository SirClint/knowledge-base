import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Home from "./pages/Home";
import DocPage from "./pages/DocPage";
import ReviewPage from "./pages/ReviewPage";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  return localStorage.getItem("token") ? <>{children}</> : <Navigate to="/login" />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<PrivateRoute><Home /></PrivateRoute>} />
        <Route path="/doc/*" element={<PrivateRoute><DocPage /></PrivateRoute>} />
        <Route path="/review" element={<PrivateRoute><ReviewPage /></PrivateRoute>} />
      </Routes>
    </BrowserRouter>
  );
}
