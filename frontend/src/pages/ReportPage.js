import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { ArrowLeft, TrendingUp, Users, BookOpen, Target, Lightbulb, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import axios from "axios";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const PRIORITY_COLORS = {
  high: "#C86B56",
  medium: "#D4Af37",
  low: "#8da399",
};

const SENTIMENT_ICONS = {
  positive: CheckCircle2,
  negative: AlertCircle,
  mixed: Target,
};

const SENTIMENT_COLORS = {
  positive: "#8da399",
  negative: "#C86B56",
  mixed: "#D4Af37",
};

function Section({ icon: Icon, title, children, delay = 0, testId }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4 }}
      data-testid={testId}
      className="mb-10"
    >
      <div className="flex items-center gap-3 mb-5">
        <div className="w-8 h-8 flex items-center justify-center bg-clay/10" style={{ borderRadius: "2px" }}>
          <Icon className="w-4 h-4 text-clay" strokeWidth={1.5} />
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

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white border border-ink-900/10 shadow-lg px-3 py-2" style={{ borderRadius: "2px", fontFamily: "'Manrope', sans-serif" }}>
        <p className="text-xs text-ink-400">Section {label}</p>
        <p className="text-sm font-semibold text-ink-900">{payload[0].value}% engagement</p>
      </div>
    );
  }
  return null;
};

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
      }
    } catch (err) {
      toast.error("Failed to load report");
    } finally {
      setLoading(false);
    }
  };

  const generateReport = async () => {
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

  const engagementData = (report?.engagement_by_section || []).map((s) => ({
    section: s.section,
    score: s.engagement_score,
    note: s.note,
  }));

  const maxEngagement = Math.max(...engagementData.map((d) => d.score), 1);

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

        {report?.coverage_note && (
          <div className="mb-8 px-4 py-3 bg-amber-50 border border-amber-200 text-amber-800 text-sm" style={{ borderRadius: "2px" }}>
            {report.coverage_note}
          </div>
        )}

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
            {/* Executive Summary */}
            <Section icon={BookOpen} title="Executive Summary" delay={0.1} testId="executive-summary-section">
              <div className="space-y-4">
                {(report.executive_summary || []).map((para, i) => (
                  <p
                    key={i}
                    className="text-base text-ink-600 leading-relaxed"
                    style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: "1.05rem", lineHeight: "1.8" }}
                  >
                    {para}
                  </p>
                ))}
              </div>
            </Section>

            {/* Engagement Heatmap */}
            {engagementData.length > 0 && (
              <Section icon={TrendingUp} title="Engagement by Section" delay={0.15} testId="engagement-chart-section">
                <p className="text-xs text-ink-400 mb-4">
                  Based on volume and intensity of reader reactions per section.
                </p>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={engagementData} margin={{ top: 4, right: 4, left: -24, bottom: 4 }}>
                    <XAxis
                      dataKey="section"
                      tick={{ fontSize: 11, fill: "#8C8885", fontFamily: "Manrope" }}
                      tickLine={false}
                      axisLine={{ stroke: "#E8E5E0" }}
                      label={{ value: "Section", position: "insideBottom", offset: -2, fontSize: 10, fill: "#8C8885" }}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: "#8C8885", fontFamily: "Manrope" }}
                      tickLine={false}
                      axisLine={false}
                      domain={[0, 100]}
                    />
                    <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(45,42,38,0.04)" }} />
                    <Bar dataKey="score" radius={[1, 1, 0, 0]}>
                      {engagementData.map((entry, index) => (
                        <Cell
                          key={index}
                          fill={entry.score === maxEngagement ? "#C86B56" : entry.score > 60 ? "#D4Af37" : "#8da399"}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div className="flex items-center gap-4 mt-3 text-xs text-ink-400">
                  <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 inline-block" style={{ background: "#C86B56", borderRadius: "1px" }} />Highest engagement</span>
                  <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 inline-block" style={{ background: "#D4Af37", borderRadius: "1px" }} />Good engagement</span>
                  <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 inline-block" style={{ background: "#8da399", borderRadius: "1px" }} />Lower engagement</span>
                </div>
              </Section>
            )}

            {/* Consensus Findings */}
            {(report.consensus_findings || []).length > 0 && (
              <Section icon={Users} title="Consensus Findings" delay={0.2} testId="consensus-findings-section">
                <div className="space-y-4">
                  {report.consensus_findings.map((finding, i) => {
                    const Icon = SENTIMENT_ICONS[finding.sentiment] || Target;
                    const color = SENTIMENT_COLORS[finding.sentiment] || "#5C5855";
                    return (
                      <div key={i} className="flex gap-4 pb-4 border-b border-ink-900/6 last:border-0 last:pb-0">
                        <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" strokeWidth={1.5} style={{ color }} />
                        <div>
                          <p className="text-sm text-ink-900 leading-relaxed mb-1">{finding.finding}</p>
                          <p className="text-xs text-ink-400">
                            {finding.reader_count} of 5 readers ·
                            {finding.sections?.length > 0 && ` Sections ${finding.sections.join(", ")}`}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Section>
            )}

            {/* Character Impressions */}
            {(report.character_impressions || []).length > 0 && (
              <Section icon={Users} title="Character Impressions" delay={0.25} testId="character-impressions-section">
                <div className="space-y-5">
                  {report.character_impressions.map((char, i) => (
                    <div key={i} className="pb-5 border-b border-ink-900/6 last:border-0 last:pb-0">
                      <h4
                        className="font-serif text-lg text-ink-900 mb-2"
                        style={{ fontFamily: "'Cormorant Garamond', serif" }}
                      >
                        {char.character}
                      </h4>
                      <p className="text-sm text-ink-600 mb-3 italic" style={{ fontFamily: "'Cormorant Garamond', serif" }}>
                        {char.overall}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {(char.impressions || []).map((imp, j) => (
                          <span key={j} className="chip text-xs">{imp}</span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Prediction Accuracy */}
            {(report.prediction_accuracy || []).length > 0 && (
              <Section icon={Target} title="Prediction Accuracy" delay={0.3} testId="prediction-accuracy-section">
                <div className="space-y-3">
                  {report.prediction_accuracy.map((pred, i) => (
                    <div key={i} className="flex gap-3 items-start p-3 bg-paper" style={{ borderRadius: "2px" }}>
                      <span
                        className="text-xs font-semibold uppercase px-2 py-0.5 flex-shrink-0 mt-0.5"
                        style={{
                          borderRadius: "2px",
                          background:
                            pred.outcome === "confirmed"
                              ? "#8da39920"
                              : pred.outcome === "denied"
                              ? "#C86B5620"
                              : "#D4Af3720",
                          color:
                            pred.outcome === "confirmed"
                              ? "#8da399"
                              : pred.outcome === "denied"
                              ? "#C86B56"
                              : "#D4Af37",
                        }}
                      >
                        {pred.outcome}
                      </span>
                      <div>
                        <p className="text-sm text-ink-900">{pred.prediction}</p>
                        {pred.note && (
                          <p className="text-xs text-ink-400 mt-1">{pred.note}</p>
                        )}
                        {pred.readers?.length > 0 && (
                          <p className="text-xs text-ink-400 mt-0.5">By: {pred.readers.join(", ")}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Recommendations */}
            {(report.recommendations || []).length > 0 && (
              <Section icon={Lightbulb} title="Actionable Recommendations" delay={0.35} testId="recommendations-section">
                <div className="space-y-4">
                  {report.recommendations.map((rec, i) => (
                    <div key={i} className="flex gap-4">
                      <div
                        className="w-1.5 flex-shrink-0 mt-1"
                        style={{
                          background: PRIORITY_COLORS[rec.priority] || "#8C8885",
                          borderRadius: "1px",
                          minHeight: "40px",
                        }}
                      />
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <h4 className="text-sm font-semibold text-ink-900">{rec.title}</h4>
                          <span
                            className="text-xs uppercase tracking-widest"
                            style={{ color: PRIORITY_COLORS[rec.priority] || "#8C8885" }}
                          >
                            {rec.priority}
                          </span>
                        </div>
                        <p className="text-sm text-ink-600 leading-relaxed">{rec.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
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
