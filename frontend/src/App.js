import React, { lazy, Suspense, useEffect } from "react";
import { MotionConfig } from "framer-motion";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import "./App.css";
import "./reading-workspace.css";
import "./policies.css";
import "./search-analytics.css";
import "./sample-reading.css";
import "./connections.css";
import ConnectAssistantPage from "./pages/ConnectAssistantPage";
const ConnectionsPage = lazy(() => import("./pages/ConnectionsPage"));
import SampleReadingPage from "./pages/SampleReadingPage";
import SearchExperience from "./components/SearchExperience";
import GuidePage from "./pages/GuidePage";
const OwnerAnalyticsPage = lazy(() => import("./pages/OwnerAnalyticsPage"));

import { AuthProvider, useAuth } from "./context/AuthContext";
import ConfirmationProvider from "./components/ConfirmationProvider";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import AuthCallback from "./pages/AuthCallback";
import VerifyEmailPage from "./pages/VerifyEmailPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const SetupPage = lazy(() => import("./pages/SetupPage"));
const ReadingPage = lazy(() => import("./pages/ReadingPage"));
const ReportPage = lazy(() => import("./pages/ReportPage"));
const BillingPage = lazy(() => import("./pages/BillingPage"));
import PolicyPage from "./pages/PolicyPage";
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
    const title = { "/connections": "Assistant connections", "/owner/analytics": "Owner analytics", "/": "A reading room for your manuscript", "/login": "Sign in", "/signup": "Create an account", "/dashboard": "Your manuscripts", "/setup": "New manuscript", "/pricing": "Plans & credits", "/billing": "Credits & billing", "/forgot-password": "Reset your password", "/reset-password": "Choose a new password", "/verify-email": "Verify your email" }[pathname] || (pathname.startsWith("/report/") ? "Editorial report" : "Reading room");
    const policyTitle = { "/terms": "Terms of service", "/privacy": "Privacy policy", "/refunds": "Refund policy" }[pathname];
    document.title = `${policyTitle || title} | Roundtable`;
    window.scrollTo(0, 0);
    if (window.location.hash) window.requestAnimationFrame(() => document.getElementById(window.location.hash.slice(1))?.scrollIntoView());
  }, [pathname]);
  return <a className="skip-link" href="#main-content">Skip to content</a>;
}

function App() {
  return (
    <div className="App">
      <MotionConfig reducedMotion="user"><AuthProvider>
        <BrowserRouter><ConfirmationProvider><RouteExperience /><SearchExperience />
          <Suspense fallback={<div className="page-width py-20" role="status">Loading Roundtable?</div>}><Routes>
            {/* Public routes */}
            <Route path="/connections" element={<ProtectedRoute><ConnectionsPage /></ProtectedRoute>} />
            <Route path="/connect-assistant" element={<ConnectAssistantPage />} />
            <Route path="/sample-reading" element={<SampleReadingPage />} />
            <Route path="/ai-beta-reader" element={<GuidePage />} />
            <Route path="/manuscript-feedback" element={<GuidePage />} />
            <Route path="/owner/analytics" element={<ProtectedRoute><OwnerAnalyticsPage /></ProtectedRoute>} />
            <Route path="/pricing" element={<BillingPage />} />
            <Route path="/terms" element={<PolicyPage kind="terms" />} />
            <Route path="/privacy" element={<PolicyPage kind="privacy" />} />
            <Route path="/refunds" element={<PolicyPage kind="refunds" />} />
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
          </Routes></Suspense>
        </ConfirmationProvider></BrowserRouter>
      </AuthProvider></MotionConfig>
      <Toaster richColors position="top-right" />
    </div>
  );
}

export default App;
