import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { BookOpen, Plus, Loader2, ChevronRight, FileText, CheckCircle, Clock } from "lucide-react";
import axios from "axios";
import { useAuth } from "../context/AuthContext";
import { UserMenu } from "../components/UserMenu";

const API = (process.env.REACT_APP_BACKEND_URL || "http://localhost:8000").replace(/\/$/, "") + "/api";

function ManuscriptCard({ ms, onClick }) {
  const totalSections = ms.total_sections || "—";
  const date = ms.created_at ? new Date(ms.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—";
  const statusColor = ms.reading_complete ? "#8da399" : "#D4Af37";
  const StatusIcon = ms.reading_complete ? CheckCircle : Clock;
  const statusLabel = ms.reading_complete ? "Complete" : "In progress";

  return (
    <motion.button
      whileHover={{ x: 2 }}
      transition={{ duration: 0.15 }}
      onClick={() => onClick(ms.id)}
      data-testid={`manuscript-card-${ms.id}`}
      className="w-full text-left border border-ink-900/8 bg-white hover:border-clay/30 transition-all p-5 flex items-start gap-4"
      style={{ borderRadius: "2px" }}
    >
      <div className="flex-shrink-0 mt-0.5">
        <FileText className="w-5 h-5 text-ink-400" strokeWidth={1.5} />
      </div>
      <div className="flex-1 min-w-0">
        <p
          className="text-sm font-semibold text-ink-900 mb-1 truncate"
          style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: "1rem" }}
        >
          {ms.title}
        </p>
        <div className="flex items-center gap-3 text-xs text-ink-400">
          <span>{ms.genre || "Fiction"}</span>
          <span>·</span>
          <span>{totalSections} sections</span>
          <span>·</span>
          <span>{date}</span>
        </div>
      </div>
      <div className="flex items-center gap-1.5 text-xs flex-shrink-0" style={{ color: statusColor }}>
        <StatusIcon className="w-3.5 h-3.5" strokeWidth={1.5} />
        <span>{statusLabel}</span>
      </div>
      <ChevronRight className="w-4 h-4 text-ink-400 flex-shrink-0 self-center" strokeWidth={1.5} />
    </motion.button>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const { user, getAuthHeaders } = useAuth();
  const [manuscripts, setManuscripts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [usage, setUsage] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get(`${API}/manuscripts`, {
          headers: getAuthHeaders(),
          withCredentials: true,
        });
        setManuscripts(res.data || []);
      } catch {
        setManuscripts([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [getAuthHeaders]);

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get(`${API}/user/usage`, {
          headers: getAuthHeaders(),
          withCredentials: true,
        });
        setUsage(res.data);
      } catch {
        setUsage(null);
      }
    })();
  }, [getAuthHeaders]);

  const handleOpenManuscript = (id) => navigate(`/read/${id}`);

  return (
    <div className="min-h-screen bg-paper" style={{ fontFamily: "'Manrope', sans-serif" }}>
      {/* Header */}
      <header className="border-b border-ink-900/8 bg-white">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-clay" strokeWidth={1.5} />
            <span className="text-lg text-ink-900" style={{ fontFamily: "'Cormorant Garamond', serif", fontWeight: 500 }}>
              Roundtable
            </span>
          </div>
          <UserMenu />
        </div>
      </header>

      {/* Body */}
      <div className="max-w-3xl mx-auto px-6 py-12">
        <div className="flex items-end justify-between mb-8">
          <div>
            <h1
              className="font-serif text-3xl text-ink-900 mb-1"
              style={{ fontFamily: "'Cormorant Garamond', serif" }}
            >
              Your manuscripts
            </h1>
            {user && <p className="text-sm text-ink-400">Welcome back, {user.name?.split(" ")[0]}.</p>}
          </div>
          <div className="flex items-center gap-4">
            {usage != null && (
              <p className="text-xs text-ink-400">
                {usage.is_admin ? "Admin — unlimited" : `Free reads: ${Math.max(0, usage.limit - usage.used)}/${usage.limit} remaining`}
              </p>
            )}
            <button
            data-testid="new-manuscript-btn"
            onClick={() => navigate("/setup")}
            className="flex items-center gap-2 bg-clay text-white text-sm px-4 py-2.5 hover:bg-clay-hover transition-colors"
            style={{ borderRadius: "2px" }}
          >
            <Plus className="w-4 h-4" strokeWidth={2} />
            New manuscript
          </button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="w-5 h-5 animate-spin text-clay" strokeWidth={1.5} />
          </div>
        ) : manuscripts.length === 0 ? (
          <div
            className="text-center py-24 border border-dashed border-ink-900/12 bg-white"
            style={{ borderRadius: "2px" }}
            data-testid="empty-dashboard"
          >
            <BookOpen className="w-8 h-8 text-ink-400 mx-auto mb-4" strokeWidth={1.5} />
            <p className="text-sm text-ink-900 font-medium mb-1">No manuscripts yet</p>
            <p className="text-xs text-ink-400 mb-6">Submit your first manuscript to get your first round of AI beta reader feedback.</p>
            <button
              data-testid="start-first-manuscript-btn"
              onClick={() => navigate("/setup")}
              className="text-sm bg-clay text-white px-4 py-2 hover:bg-clay-hover transition-colors"
              style={{ borderRadius: "2px" }}
            >
              Get started
            </button>
          </div>
        ) : (
          <div className="space-y-3" data-testid="manuscripts-list">
            {manuscripts.map((ms) => (
              <ManuscriptCard key={ms.id} ms={ms} onClick={handleOpenManuscript} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
