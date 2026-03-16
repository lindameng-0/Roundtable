import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import {
  ArrowLeft,
  BookOpen,
  Target,
  Loader2,
  HelpCircle,
  MessageSquare,
  TrendingDown,
  Sparkles,
  Users,
} from "lucide-react";
import axios from "axios";
import { getApi } from "../apiConfig";

const API = getApi();

function Section({ icon: Icon, title, children, delay = 0, testId, accent }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4 }}
      data-testid={testId}
      className="mb-10"
    >
      <div className="flex items-center gap-3 mb-5">
        <div
          className="w-8 h-8 flex items-center justify-center"
          style={{ borderRadius: "2px", background: accent ? `${accent}15` : "rgba(200,107,86,0.1)" }}
        >
          <Icon className="w-4 h-4" strokeWidth={1.5} style={{ color: accent || "#C86B56" }} />
        </div>
        <h2
          className="font-serif text-2xl text-ink-900"
          style={{ fontFamily: "'Cormorant Garamond', serif" }}
        >
          {title}
        </h2>
      </div>
      <div className="border border-ink-900/8 bg-white p-6" style={{ borderRadius: "2px" }}>
        {children}
      </div>
    </motion.section>
  );
}

export default function ReportPage() {
  const { manuscriptId } = useParams();
  const navigate = useNavigate();
  const [report, setReport] = useState(null);
  const [manuscript, setManuscript] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    loadReport();
  }, [manuscriptId]);

  const loadReport = async () => {
    setLoading(true);
    try {
      const [repRes, mRes] = await Promise.all([
        axios.get(`${API}/manuscripts/${manuscriptId}/editor-report`).catch(() => null),
        axios.get(`${API}/manuscripts/${manuscriptId}`),
      ]);
      setManuscript(mRes.data);
      if (repRes?.data?.report_json) {
        setReport(repRes.data.report_json);
      } else if (repRes?.data?.report) {
        setReport(repRes.data.report);
      }
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail ?? err.response?.data?.message;
      const msg = typeof detail === "string" ? detail : null;
      if (status === 404) {
        toast.error(msg || "Manuscript not found");
      } else {
        toast.error(msg || "Failed to load report");
      }
    } finally {
      setLoading(false);
    }
  };

  const generateReport = async () => {
    if (!manuscriptId) {
      toast.error("Missing manuscript. Open the report from the reading page.");
      return;
    }
    setGenerating(true);
    try {
      const res = await axios.post(`${API}/manuscripts/${manuscriptId}/editor-report`);
      setReport(res.data.report);
      toast.success("Editor report generated");
    } catch (err) {
      const detail = err.response?.data?.detail ?? err.response?.data?.message;
      const msg = typeof detail === "string" ? detail : (Array.isArray(detail) ? detail.map((d) => d.msg ?? d).join(", ") : null);
      toast.error(msg || "Failed to generate report. Make sure you've read at least one section.");
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-clay" strokeWidth={1.5} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper" style={{ fontFamily: "'Manrope', sans-serif" }}>
      {/* Header */}
      <header className="border-b border-ink-900/8 bg-paper sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              data-testid="back-to-reading-btn"
              onClick={() => navigate(`/read/${manuscriptId}`)}
              className="flex items-center gap-2 text-sm text-ink-600 hover:text-ink-900 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" strokeWidth={1.5} />
              Back to reading
            </button>
            <div className="h-4 w-px bg-ink-900/10" />
            <h1 className="font-serif text-lg text-ink-900" style={{ fontFamily: "'Cormorant Garamond', serif" }}>
              Editor Report
            </h1>
          </div>
          {manuscript && (
            <p className="text-sm text-ink-400 hidden sm:block">{manuscript.title}</p>
          )}
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-8 py-12">
        {/* Title */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-12"
        >
          <p className="text-xs text-ink-400 uppercase tracking-widest mb-3">Roundtable Editorial Review</p>
          <h1
            className="font-serif text-5xl text-ink-900 mb-4"
            style={{ fontFamily: "'Cormorant Garamond', serif" }}
          >
            {manuscript?.title || "Untitled Manuscript"}
          </h1>
          <div className="flex items-center gap-4 text-sm text-ink-400">
            {manuscript?.genre && <span className="chip">{manuscript.genre}</span>}
            {manuscript?.target_audience && <span className="chip">{manuscript.target_audience}</span>}
          </div>
        </motion.div>

        {!report ? (
          <div className="text-center py-20 border border-ink-900/8 bg-white" style={{ borderRadius: "2px" }}>
            <BookOpen className="w-8 h-8 text-ink-400 mx-auto mb-4" strokeWidth={1.5} />
            <h3 className="font-serif text-xl text-ink-900 mb-2" style={{ fontFamily: "'Cormorant Garamond', serif" }}>
              No report yet
            </h3>
            <p className="text-sm text-ink-400 mb-6 max-w-sm mx-auto">
              Finish reading at least one section, then generate your editor report.
            </p>
            <button
              data-testid="generate-report-main-btn"
              onClick={generateReport}
              disabled={generating}
              className="flex items-center gap-2 bg-clay hover:bg-clay-hover text-white px-6 py-3 text-sm font-medium mx-auto transition-all"
              style={{ borderRadius: "2px" }}
            >
              {generating ? (
                <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.5} />
              ) : (
                <Target className="w-4 h-4" strokeWidth={1.5} />
              )}
              {generating ? "Generating..." : "Generate Editor Report"}
            </button>
          </div>
        ) : (
          <>
            {/* 1. Did it land? */}
            <Section
              icon={Target}
              title="Did it land?"
              delay={0.1}
              testId="did-it-land-section"
              accent="#C86B56"
            >
              <DidItLandContent didItLand={report.did_it_land} />
            </Section>

            {/* 2. Where did engagement drop? */}
            {(report.engagement_drop || []).length > 0 && (
              <Section
                icon={TrendingDown}
                title="Where did engagement drop?"
                delay={0.15}
                testId="engagement-drop-section"
                accent="#8C8885"
              >
                <EngagementDropContent items={report.engagement_drop} />
              </Section>
            )}

            {/* 3. What readers disagree about */}
            {(report.what_readers_disagree_about || []).length > 0 && (
              <Section
                icon={Users}
                title="What readers disagree about"
                delay={0.2}
                testId="disagreements-section"
                accent="#D4Af37"
              >
                <DisagreementsContent items={report.what_readers_disagree_about} />
              </Section>
            )}

            {/* 4. Open questions */}
            {(report.open_questions || []).length > 0 && (
              <Section
                icon={HelpCircle}
                title="Open questions"
                delay={0.25}
                testId="open-questions-section"
                accent="#5C9B8E"
              >
                <OpenQuestionsContent items={report.open_questions} />
              </Section>
            )}

            {/* 5. Strongest moments */}
            {(report.strongest_moments || []).length > 0 && (
              <Section
                icon={Sparkles}
                title="Strongest moments"
                delay={0.3}
                testId="strongest-moments-section"
                accent="#8da399"
              >
                <StrongestMomentsContent items={report.strongest_moments} />
              </Section>
            )}

            {/* Regenerate */}
            <div className="text-center pt-4 pb-8">
              <button
                data-testid="regenerate-report-btn"
                onClick={generateReport}
                disabled={generating}
                className="flex items-center gap-2 text-sm text-ink-600 hover:text-clay border border-ink-900/12 hover:border-clay px-5 py-2.5 mx-auto transition-all"
                style={{ borderRadius: "2px" }}
              >
                {generating ? (
                  <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.5} />
                ) : (
                  <Target className="w-4 h-4" strokeWidth={1.5} />
                )}
                Regenerate Report
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ─── Section content components ─────────────────────────────────────────── */

function DidItLandContent({ didItLand }) {
  if (!didItLand) {
    return <p className="text-sm text-ink-400">No intent data collected from readers.</p>;
  }
  // didItLand is a string (possibly multi-paragraph)
  const paragraphs = typeof didItLand === "string"
    ? didItLand.split(/\n{2,}/).filter(Boolean)
    : [String(didItLand)];

  return (
    <div className="space-y-4">
      {paragraphs.map((para, i) => (
        <p
          key={i}
          className="text-base text-ink-600 leading-relaxed"
          style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: "1.05rem", lineHeight: "1.8" }}
        >
          {para}
        </p>
      ))}
    </div>
  );
}

function EngagementDropContent({ items }) {
  if (!items || items.length === 0) {
    return (
      <p className="text-sm text-ink-400">
        No sections with significantly lower engagement identified.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div
          key={i}
          className="flex items-start gap-3 py-2.5 border-b border-ink-900/5 last:border-0"
        >
          <span
            className="text-xs font-semibold px-2 py-0.5 flex-shrink-0 mt-0.5"
            style={{
              background: "rgba(140,136,133,0.12)",
              color: "#5C5855",
              borderRadius: "2px",
            }}
          >
            §{item.section}
          </span>
          <p className="text-sm text-ink-600 leading-relaxed">
            {item.note || "Lower reader engagement noted."}
          </p>
        </div>
      ))}
    </div>
  );
}

function DisagreementsContent({ items }) {
  if (!items || items.length === 0) {
    return <p className="text-sm text-ink-400">No significant disagreements between readers.</p>;
  }
  return (
    <div className="space-y-4">
      {items.map((item, i) => (
        <div
          key={i}
          className="flex gap-3 pb-4 border-b border-ink-900/5 last:border-0 last:pb-0"
        >
          <div
            className="w-1 flex-shrink-0 mt-1.5"
            style={{ background: "#D4Af37", borderRadius: "1px", minHeight: "32px" }}
          />
          <p
            className="text-sm text-ink-600 leading-relaxed"
            style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: "1rem", lineHeight: "1.7" }}
          >
            {item}
          </p>
        </div>
      ))}
    </div>
  );
}

function OpenQuestionsContent({ items }) {
  if (!items || items.length === 0) {
    return <p className="text-sm text-ink-400">No open questions from readers.</p>;
  }
  return (
    <div className="space-y-3">
      {items.map((item, i) => {
        const question = typeof item === "string" ? item : item.question;
        const multiple = typeof item === "object" ? item.asked_by_multiple : false;
        return (
          <div
            key={i}
            className="flex items-start gap-3 p-3"
            style={{
              background: multiple ? "rgba(200, 107, 86, 0.06)" : "#FAFAF9",
              borderLeft: multiple ? "2px solid #C86B56" : "2px solid rgba(45,42,38,0.08)",
              borderRadius: "0 2px 2px 0",
            }}
          >
            <HelpCircle
              className="w-3.5 h-3.5 flex-shrink-0 mt-0.5"
              strokeWidth={1.5}
              style={{ color: multiple ? "#C86B56" : "#8C8885" }}
            />
            <div className="flex-1 min-w-0">
              <p
                className="text-sm text-ink-700 leading-relaxed"
                style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: "1rem", fontStyle: "italic" }}
              >
                {question}
              </p>
              {multiple && (
                <p className="text-xs text-clay mt-1">Asked by multiple readers</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function StrongestMomentsContent({ items }) {
  if (!items || items.length === 0) {
    return <p className="text-sm text-ink-400">No standout moments curated.</p>;
  }
  return (
    <div className="space-y-4">
      {items.map((item, i) => (
        <div
          key={i}
          className="pb-4 border-b border-ink-900/5 last:border-0 last:pb-0"
        >
          <div className="flex items-center gap-2 mb-2">
            <span
              className="text-xs px-2 py-0.5 font-medium"
              style={{
                background: "rgba(141,163,153,0.15)",
                color: "#4a7a6b",
                borderRadius: "2px",
              }}
            >
              {item.reader}
            </span>
            {item.section && (
              <span className="text-xs text-ink-400">§{item.section}</span>
            )}
          </div>
          <p
            className="text-sm text-ink-700 leading-relaxed"
            style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: "1.05rem", lineHeight: "1.75" }}
          >
            {item.quote_or_summary}
          </p>
        </div>
      ))}
    </div>
  );
}
