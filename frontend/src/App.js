import React, { useEffect } from "react";
import { MotionConfig } from "framer-motion";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import "./App.css";

import { AuthProvider, useAuth } from "./context/AuthContext";
import ConfirmationProvider from "./components/ConfirmationProvider";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import AuthCallback from "./pages/AuthCallback";
import VerifyEmailPage from "./pages/VerifyEmailPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import DashboardPage from "./pages/DashboardPage";
import SetupPage from "./pages/SetupPage";
import ReadingPage from "./pages/ReadingPage";
import ReportPage from "./pages/ReportPage";
import BillingPage from "./pages/BillingPage";
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

/** If already logged in, redirect /login → /setup (manuscript page). */
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

/** Authenticated → /dashboard, guest → /login */
function RootRedirect() {
  const { user } = useAuth();
  return user ? <Navigate to="/dashboard" replace /> : <HomePage />;
}

function RouteExperience() {
  const { pathname } = useLocation();
  useEffect(() => {
    const title = { "/": "A reading room for your manuscript", "/login": "Sign in", "/signup": "Create an account", "/dashboard": "Your manuscripts", "/setup": "New manuscript", "/pricing": "Plans & credits", "/billing": "Credits & billing", "/forgot-password": "Reset your password", "/reset-password": "Choose a new password", "/verify-email": "Verify your email" }[pathname] || (pathname.startsWith("/report/") ? "Editorial report" : "Reading room");
    document.title = `${title} | Roundtable`;
    window.scrollTo(0, 0);
    if (window.location.hash) window.requestAnimationFrame(() => document.getElementById(window.location.hash.slice(1))?.scrollIntoView());
  }, [pathname]);
  return <a className="skip-link" href="#main-content">Skip to content</a>;
}

function App() {
  return (
    <div className="App">
      <MotionConfig reducedMotion="user"><AuthProvider>
        <BrowserRouter><ConfirmationProvider><RouteExperience />
          <Routes>
            {/* Public routes */}
            <Route path="/pricing" element={<BillingPage />} />
            <Route path="/billing" element={<ProtectedRoute><BillingPage /></ProtectedRoute>} />
            <Route path="/login" element={<PublicOnlyRoute><LoginPage /></PublicOnlyRoute>} />
            <Route path="/signup" element={<PublicOnlyRoute><LoginPage initialMode="signup" /></PublicOnlyRoute>} />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/verify-email" element={<PublicOnlyRoute><VerifyEmailPage /></PublicOnlyRoute>} />
            <Route path="/forgot-password" element={<PublicOnlyRoute><ForgotPasswordPage /></PublicOnlyRoute>} />
            {/* Reset links must remain reachable even when an old session is active. */}
            <Route path="/reset-password" element={<ResetPasswordPage />} />

            {/* Protected routes (require auth) */}
            <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />

            {/* Application routes require an account. */}
            <Route path="/setup" element={<ProtectedRoute><SetupPage /></ProtectedRoute>} />
            <Route path="/read/:manuscriptId" element={<ProtectedRoute><ReadingPage /></ProtectedRoute>} />
            <Route path="/report/:manuscriptId" element={<ProtectedRoute><ReportPage /></ProtectedRoute>} />

            {/* Root: redirect based on auth */}
            <Route path="/" element={<RootRedirect />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </ConfirmationProvider></BrowserRouter>
      </AuthProvider></MotionConfig>
      <Toaster richColors position="top-right" />
    </div>
  );
}

export default App;
