import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import "./App.css";

import { AuthProvider, useAuth } from "./context/AuthContext";
import LoginPage from "./pages/LoginPage";
import AuthCallback from "./pages/AuthCallback";
import DashboardPage from "./pages/DashboardPage";
import SetupPage from "./pages/SetupPage";
import ReadingPage from "./pages/ReadingPage";
import ReportPage from "./pages/ReportPage";
import { Loader2 } from "lucide-react";

/** Redirect unauthenticated users to /login; show spinner while loading. */
function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin text-clay" strokeWidth={1.5} />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

/** If already logged in, redirect /login → /dashboard. */
function PublicOnlyRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin text-clay" strokeWidth={1.5} />
      </div>
    );
  }
  if (user) return <Navigate to="/dashboard" replace />;
  return children;
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<PublicOnlyRoute><LoginPage /></PublicOnlyRoute>} />
            <Route path="/auth/callback" element={<AuthCallback />} />

            {/* Protected routes (require auth) */}
            <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />

            {/* Optional-auth routes (sign-in not required) */}
            <Route path="/setup" element={<SetupPage />} />
            <Route path="/read/:manuscriptId" element={<ReadingPage />} />
            <Route path="/report/:manuscriptId" element={<ReportPage />} />

            {/* Root: redirect based on auth */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
      <Toaster richColors position="top-right" />
    </div>
  );
}

export default App;
