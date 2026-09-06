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
  AlertTriangle,
  CheckCircle,
  Wrench,
  ListChecks,
  FileText,
  History,
  Download,
  Trash2,
  Printer,
} from "lucide-react";
import axios from "axios";
import { getApi } from "../apiConfig";
import { manuscriptRequestConfig } from "../manuscriptAccess";

const API = getApi();

const INTERNAL_CITATION = /\s*\[(?=[^\]\n]*(?:\bp-\d{6}\b|\bjournal\b|\bevidence\b))[^\]\n]{1,500}\]/gi;

function cleanInternalCitations(value) {
  if (typeof value === "string") return value.replace(INTERNAL_CITATION, "").replace(/[ \t]{2,}/g, " ").trim();
  if (Array.isArray(value)) return value.map(cleanInternalCitations);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cleanInternalCitations(item)]));
  }
  return value;
}

function normalizeReport(raw) {
  if (!raw || typeof raw !== "object") return null;
  raw = cleanInternalCitations(raw);
  return {
    ...raw,
    did_it_land: raw.did_it_land ?? null,
    engagement_map: raw.engagement_map || (raw.engagement_drop || []).map((item) => ({
      section: item.section,
      engagement_level: "low",
      notes: item.note || "Lower reader engagement noted.",
    })),
    disagreements: raw.disagreements || (raw.what_readers_disagree_about || []).map((item) =>
      typeof item === "string" ? { topic: item, positions: {}, significance: "" } : item
    ),
    unresolved_questions: raw.unresolved_questions || (raw.open_questions || []).map((item) =>
      typeof item === "string"
        ? { question: item, asked_by: [], resolved: false }
        : { ...item, asked_by: item.asked_by || [], resolved: item.resolved ?? false }
    ),
  };
}

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
  const [copyEditing, setCopyEditing] = useState(false);
  const [versions, setVersions] = useState([]);
  const [viewingVersion, setViewingVersion] = useState(null);
  const [budget, setBudget] = useState(null);

  const waitForJob = async (jobId) => {
    while (true) {
      const response = await axios.get(`${API}/jobs/${jobId}`, manuscriptRequestConfig(manuscriptId));
      const job = response.data;
      if (job.status === "completed") return job.result || {};
      if (job.status === "failed") throw new Error(job.error || "AI job failed after automatic retries");
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  };

  useEffect(() => {
    loadReport();
  }, [manuscriptId]);

  const loadReport = async () => {
    setLoading(true);
    try {
      const [repRes, mRes, versionRes, budgetRes] = await Promise.all([
        axios.get(`${API}/manuscripts/${manuscriptId}/editor-report`, manuscriptRequestConfig(manuscriptId)).catch(() => null),
        axios.get(`${API}/manuscripts/${manuscriptId}`, manuscriptRequestConfig(manuscriptId)),
        axios.get(`${API}/manuscripts/${manuscriptId}/editor-report/versions`, manuscriptRequestConfig(manuscriptId)).catch(() => ({ data: [] })),
        axios.get(`${API}/manuscripts/${manuscriptId}/budget`, manuscriptRequestConfig(manuscriptId)).catch(() => ({ data: null })),
      ]);
      setManuscript(mRes.data);
      setVersions(versionRes.data || []);
      setViewingVersion(null);
      setBudget(budgetRes.data);
      if (repRes?.data?.report_json) {
        setReport(normalizeReport(repRes.data.report_json));
      } else if (repRes?.data?.report) {
        setReport(normalizeReport(repRes.data.report));
      } else {
        const jobs = await axios.get(
          `${API}/manuscripts/${manuscriptId}/jobs?job_type=editor_report`,
          manuscriptRequestConfig(manuscriptId),
        ).catch(() => ({ data: [] }));
        const active = (jobs.data || []).find((job) => job.status === "queued" || job.status === "running");
        if (active) {
          setGenerating(true);
          waitForJob(active.id).then(async (result) => {
            setReport(normalizeReport(result.report));
            await refreshVersions();
            await refreshBudget();
            toast.success("Editor report generated");
          }).catch((error) => toast.error(error.message)).finally(() => setGenerating(false));
        }
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

  const generateReport = async (force = false) => {
    if (!manuscriptId) {
      toast.error("Missing manuscript. Open the report from the reading page.");
      return;
    }
    if (force || !report) {
      const approved = await confirmPaidOperation(force ? "editor_regeneration" : "editor", force ? "Regenerate the editor report" : "Generate the editor report");
      if (!approved) return;
    }
    setGenerating(true);
    try {
      const key = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      const res = await axios.post(
        `${API}/manuscripts/${manuscriptId}/editor-report${force ? "?force=true" : ""}`,
        {}, manuscriptRequestConfig(manuscriptId, { headers: { "Idempotency-Key": force ? key : `editor-report-${manuscriptId}-initial` } }),
      );
      const result = res.status === 202 ? await waitForJob(res.data.id) : res.data;
      setReport(normalizeReport(result.report));
      setViewingVersion(null);
      await refreshVersions();
      await refreshBudget();
      toast.success("Editor report generated");
    } catch (err) {
      const detail = err.response?.data?.detail ?? err.response?.data?.message;
      const msg = typeof detail === "string" ? detail : (Array.isArray(detail) ? detail.map((d) => d.msg ?? d).join(", ") : err.message);
      toast.error(msg || "Failed to generate report. Make sure you've read at least one section.");
    } finally {
      setGenerating(false);
    }
  };

  const refreshVersions = async () => {
    const res = await axios.get(`${API}/manuscripts/${manuscriptId}/editor-report/versions`, manuscriptRequestConfig(manuscriptId));
    setVersions(res.data || []);
  };

  const refreshBudget = async () => {
    const res = await axios.get(`${API}/manuscripts/${manuscriptId}/budget`, manuscriptRequestConfig(manuscriptId));
    setBudget(res.data);
  };

  const confirmPaidOperation = async (operation, label) => {
    try {
      const res = await axios.get(`${API}/manuscripts/${manuscriptId}/cost-estimate?operation=${operation}`, manuscriptRequestConfig(manuscriptId));
      const estimate = Number(res.data.estimated_cost_usd || 0);
      const remaining = res.data.budget?.remaining_usd;
      if (!res.data.can_start) {
        toast.error(`${label} is estimated at $${estimate.toFixed(3)}, above the $${Number(remaining || 0).toFixed(3)} remaining budget.`);
        return false;
      }
      return window.confirm(`${label}? This is estimated to use about $${estimate.toFixed(3)} of AI credit. Provider billing can vary.`);
    } catch (err) {
      toast.error("Could not verify the cost estimate. Nothing was generated.");
      return false;
    }
  };

  const showReportVersion = async (version) => {
    try {
      const url = version
        ? `${API}/manuscripts/${manuscriptId}/editor-report/versions/${version}`
        : `${API}/manuscripts/${manuscriptId}/editor-report`;
      const res = await axios.get(url, manuscriptRequestConfig(manuscriptId));
      setReport(normalizeReport(res.data.report_json || res.data.report));
      setViewingVersion(version || null);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not load that report version");
    }
  };

  const generateCopyEdit = async () => {
    const approved = await confirmPaidOperation("copyedit", "Generate the optional copy-edit appendix");
    if (!approved) return;
    setCopyEditing(true);
    try {
      const key = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      const res = await axios.post(
        `${API}/manuscripts/${manuscriptId}/editor-report/copy-edit`,
        {},
        manuscriptRequestConfig(manuscriptId, { headers: { "Idempotency-Key": `copy-edit-${manuscriptId}-${key}` } })
      );
      const result = res.status === 202 ? await waitForJob(res.data.id) : res.data;
      setReport((current) => ({ ...current, copy_edit_appendix: result.copy_edit_appendix }));
      setViewingVersion(null);
      await refreshVersions();
      await refreshBudget();
      toast.success("Copy-edit appendix generated");
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || "Copy edit failed");
    } finally {
      setCopyEditing(false);
    }
  };

  const exportWorkspace = async () => {
    try {
      const res = await axios.get(`${API}/manuscripts/${manuscriptId}/export`, manuscriptRequestConfig(manuscriptId));
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${(manuscript?.title || "roundtable").replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "") || "roundtable"}-workspace.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast.success("Workspace exported");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Export failed");
    }
  };

  const deleteWorkspace = async () => {
    if (!window.confirm(`Permanently delete “${manuscript?.title || "this manuscript"}” and all reader data? This cannot be undone.`)) return;
    try {
      await axios.delete(`${API}/manuscripts/${manuscriptId}?confirm=true`, manuscriptRequestConfig(manuscriptId));
      toast.success("Manuscript deleted");
      navigate("/setup");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Deletion failed");
    }
  };

  const printReport = () => window.print();

  if (loading) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-clay" strokeWidth={1.5} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper report-document" style={{ fontFamily: "'Manrope', sans-serif" }}>
      {/* Header */}
      <header className="border-b border-ink-900/8 bg-paper sticky top-0 z-10 no-print">
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
          {budget && (
            <div className="mt-5 max-w-md border border-ink-900/10 bg-white px-4 py-3 text-xs text-ink-500 no-print" data-testid="report-cost-summary">
              AI spend ${Number(budget.spent_usd || 0).toFixed(4)} of ${Number(budget.limit_usd || 0).toFixed(2)}
              {budget.reserved_usd > 0 && ` · $${Number(budget.reserved_usd).toFixed(4)} currently reserved`}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 mt-5 no-print">
            <button onClick={printReport} className="flex items-center gap-1.5 text-xs text-ink-600 border border-ink-900/12 px-3 py-2 hover:border-clay hover:text-clay transition-colors" style={{ borderRadius: "2px" }}>
              <Printer className="w-3.5 h-3.5" /> Print / Save PDF
            </button>
            <button onClick={exportWorkspace} className="flex items-center gap-1.5 text-xs text-ink-600 border border-ink-900/12 px-3 py-2 hover:border-clay hover:text-clay transition-colors" style={{ borderRadius: "2px" }}>
              <Download className="w-3.5 h-3.5" /> Export workspace
            </button>
            <button onClick={deleteWorkspace} className="flex items-center gap-1.5 text-xs text-ink-400 border border-ink-900/12 px-3 py-2 hover:border-red-400 hover:text-red-600 transition-colors" style={{ borderRadius: "2px" }}>
              <Trash2 className="w-3.5 h-3.5" /> Delete
            </button>
          </div>
        </motion.div>

        {report && versions.length > 0 && (
          <div className="mb-8 flex flex-wrap items-center gap-2 text-xs no-print" data-testid="report-history">
            <History className="w-4 h-4 text-ink-400 mr-1" />
            <span className="text-ink-500 mr-1">Report history</span>
            <button onClick={() => showReportVersion(null)} className={`px-2.5 py-1.5 border transition-colors ${viewingVersion === null ? "border-clay text-clay bg-clay/5" : "border-ink-900/10 text-ink-500 hover:border-clay"}`}>Current</button>
            {versions.map((item) => (
              <button key={item.version} onClick={() => showReportVersion(item.version)} title={`${item.reason} · ${new Date(item.created_at).toLocaleString()}`} className={`px-2.5 py-1.5 border transition-colors ${viewingVersion === item.version ? "border-clay text-clay bg-clay/5" : "border-ink-900/10 text-ink-500 hover:border-clay"}`}>
                v{item.version}
              </button>
            ))}
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
              onClick={() => generateReport(false)}
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
            {report.schema_version >= 3 ? (
              <EditorV3Report
                report={report}
                manuscriptId={manuscriptId}
                copyEditing={copyEditing}
                onCopyEdit={generateCopyEdit}
              />
            ) : (
            <>
            {report.story_overview && (
              <Section icon={BookOpen} title="Story overview" delay={0.05} testId="story-overview-section">
                <StoryOverviewContent overview={report.story_overview} />
              </Section>
            )}

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

            {(report.engagement_map || []).length > 0 && (
              <Section
                icon={TrendingDown}
                title="Engagement map"
                delay={0.15}
                testId="engagement-map-section"
                accent="#8C8885"
              >
                <EngagementMapContent items={report.engagement_map} />
              </Section>
            )}

            {(report.disagreements || []).length > 0 && (
              <Section
                icon={Users}
                title="What readers disagree about"
                delay={0.2}
                testId="disagreements-section"
                accent="#D4Af37"
              >
                <DisagreementsContent items={report.disagreements} />
              </Section>
            )}

            {(report.unresolved_questions || []).length > 0 && (
              <Section
                icon={HelpCircle}
                title="Open questions"
                delay={0.25}
                testId="open-questions-section"
                accent="#5C9B8E"
              >
                <OpenQuestionsContent items={report.unresolved_questions} />
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

            {(report.character_perception_map || []).length > 0 && (
              <Section icon={Users} title="Character perception" delay={0.35} testId="character-perception-section">
                <CharacterPerceptionContent items={report.character_perception_map} />
              </Section>
            )}

            {(report.prediction_tracker || []).length > 0 && (
              <Section icon={Target} title="Reader predictions" delay={0.4} testId="prediction-tracker-section">
                <PredictionTrackerContent items={report.prediction_tracker} />
              </Section>
            )}

            {report.heart_of_story?.synthesis && (
              <Section icon={MessageSquare} title="Heart of the story" delay={0.45} testId="heart-of-story-section">
                <p className="text-base text-ink-600 leading-relaxed">{report.heart_of_story.synthesis}</p>
              </Section>
            )}

            {(report.moments_of_consensus || []).length > 0 && (
              <Section icon={Sparkles} title="Moments of consensus" delay={0.5} testId="consensus-section">
                <ConsensusContent items={report.moments_of_consensus} />
              </Section>
            )}
            </>
            )}

            {/* Regenerate */}
            <div className="text-center pt-4 pb-8 no-print">
              <button
                data-testid="regenerate-report-btn"
                onClick={() => generateReport(true)}
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

function EvidenceLinks({ items = [], manuscriptId }) {
  if (!items.length) return null;
  return <div className="flex flex-wrap gap-2 mt-3">{items.map((ref, index) => {
    const label = [ref.reader, ref.section ? `§${ref.section}` : null].filter(Boolean).join(" · ") || "Evidence";
    const href = ref.paragraph_id ? `/read/${manuscriptId}#${encodeURIComponent(ref.paragraph_id)}` : `/read/${manuscriptId}`;
    return <a key={`${ref.evidence_id || ref.paragraph_id || label}-${index}`} href={href} title={ref.note || "Open source evidence"} className="text-xs text-clay hover:text-clay-hover border border-clay/20 px-2 py-1 transition-colors" style={{ borderRadius: "2px" }}>{label}</a>;
  })}</div>;
}

function FindingList({ items = [], manuscriptId, emptyText }) {
  if (!items.length) return <p className="text-sm text-ink-400">{emptyText}</p>;
  return <div className="space-y-5">{items.map((item, index) => (
    <div key={index} className="pb-5 border-b border-ink-900/5 last:border-0 last:pb-0">
      <p className="font-medium text-ink-800">{item.title}</p>
      <p className="text-sm text-ink-600 leading-relaxed mt-1">{item.analysis}</p>
      <EvidenceLinks items={item.evidence} manuscriptId={manuscriptId} />
    </div>
  ))}</div>;
}

function EditorV3Report({ report, manuscriptId, copyEditing, onCopyEdit }) {
  const summary = report.executive_summary || {};
  const response = report.reader_response || {};
  const appendix = report.copy_edit_appendix;
  const integrityLabels = {
    confirmed_contradiction: "Confirmed contradiction",
    likely_inconsistency: "Likely inconsistency",
    reader_confusion: "Reader confusion",
    ambiguity_or_insufficient_evidence: "Ambiguity / insufficient evidence",
  };
  const priorityStyles = { critical: "bg-red-50 text-red-700", important: "bg-amber-50 text-amber-700", optional: "bg-ink-900/5 text-ink-500" };
  const engagementStyles = {
    high: { width: "100%", color: "#6F8C7E", label: "High" },
    medium: { width: "70%", color: "#D4AF37", label: "Medium" },
    mixed: { width: "50%", color: "#A28B72", label: "Mixed" },
    low: { width: "28%", color: "#C86B56", label: "Low" },
    unknown: { width: "12%", color: "#8C8885", label: "Unknown" },
  };

  return <>
    <Section icon={FileText} title="Executive summary" delay={0.05} testId="executive-summary-section">
      <div className="space-y-6">
        <div><p className="text-xs uppercase tracking-widest text-ink-400 mb-2">Synopsis</p><p className="text-base text-ink-700 leading-relaxed whitespace-pre-line">{summary.synopsis}</p></div>
        <div><p className="text-xs uppercase tracking-widest text-ink-400 mb-2">Overall reader experience</p><p className="text-sm text-ink-600 leading-relaxed">{summary.overall_reader_experience}</p></div>
        <div className="grid md:grid-cols-2 gap-4">
          <div className="bg-sage/10 p-4"><p className="text-xs uppercase tracking-widest text-ink-400 mb-2">Strongest asset</p><p className="text-sm text-ink-700">{summary.strongest_asset}</p></div>
          <div className="bg-clay/10 p-4"><p className="text-xs uppercase tracking-widest text-ink-400 mb-2">Main friction</p><p className="text-sm text-ink-700">{summary.main_friction}</p></div>
        </div>
        <div><p className="text-xs uppercase tracking-widest text-ink-400 mb-2">Top priorities</p><ol className="space-y-2">{(summary.top_priorities || []).map((priority, index) => <li key={index} className="flex gap-3 text-sm text-ink-700"><span className="text-clay font-medium">{index + 1}.</span>{priority}</li>)}</ol></div>
      </div>
    </Section>

    <Section icon={Users} title="Reader response" delay={0.1} testId="reader-response-section">
      <div className="grid md:grid-cols-2 gap-x-8 gap-y-8">{[
        ["What worked", response.what_worked, "No repeated strength was identified."],
        ["Friction points", response.friction_points, "No repeated friction was identified."],
        ["Emotional peaks", response.emotional_peaks, "No clear emotional peak was identified."],
        ["Meaningful disagreements", response.meaningful_disagreements, "Readers largely agreed."],
      ].map(([title, items, empty]) => <div key={title}><h3 className="font-medium text-sm text-ink-800 mb-3">{title}</h3><FindingList items={items} manuscriptId={manuscriptId} emptyText={empty} /></div>)}</div>
    </Section>

    {(response.meaningful_disagreements || []).length > 0 && (
      <Section icon={Users} title="Reader divergence" delay={0.12} testId="reader-divergence-visual">
        <div className="space-y-5">{response.meaningful_disagreements.map((item, index) => (
          <div key={index} className="border-l-2 border-gold pl-4">
            <p className="font-medium text-sm text-ink-800">{item.title}</p>
            <p className="text-sm text-ink-600 mt-1 leading-relaxed">{item.analysis}</p>
            <div className="flex flex-wrap gap-1.5 mt-3">{[...new Set((item.evidence || []).map((ref) => ref.reader).filter(Boolean))].map((reader) => <span key={reader} className="chip">{reader}</span>)}</div>
            <EvidenceLinks items={item.evidence} manuscriptId={manuscriptId} />
          </div>
        ))}</div>
      </Section>
    )}

    <Section icon={AlertTriangle} title="Story integrity" delay={0.15} testId="story-integrity-section">
      {(report.story_integrity || []).length ? <div className="space-y-5">{report.story_integrity.map((item, index) => (
        <div key={index} className="pb-5 border-b border-ink-900/5 last:border-0">
          <div className="flex flex-wrap items-center gap-2 mb-2"><span className="text-xs px-2 py-1 bg-ink-900/5 text-ink-600">{integrityLabels[item.classification]}</span><span className="text-xs text-ink-400">{item.severity} severity · {Math.round((item.confidence || 0) * 100)}% confidence</span></div>
          <p className="font-medium text-ink-800">{item.title}</p><p className="text-sm text-ink-600 mt-1 leading-relaxed">{item.explanation}</p><EvidenceLinks items={item.evidence} manuscriptId={manuscriptId} />
        </div>
      ))}</div> : <p className="text-sm text-ink-500">No evidence-supported continuity problem was found.</p>}
    </Section>

    {(report.characters || []).length > 0 && <Section icon={Users} title="Characters" delay={0.2} testId="characters-v3-section"><div className="space-y-6">{report.characters.map((character, index) => (
      <div key={index} className="pb-6 border-b border-ink-900/5 last:border-0"><h3 className="font-serif text-xl text-ink-900">{character.name}</h3><p className="text-sm text-ink-600 mt-2"><span className="font-medium">Reader perception:</span> {character.reader_perception}</p><p className="text-sm text-ink-600 mt-2"><span className="font-medium">Motivation and consistency:</span> {character.motivation_and_consistency}</p>{character.relationship_notes && <p className="text-sm text-ink-600 mt-2"><span className="font-medium">Relationships:</span> {character.relationship_notes}</p>}<EvidenceLinks items={character.evidence} manuscriptId={manuscriptId} /></div>
    ))}</div></Section>}

    <Section icon={TrendingDown} title="Pacing and structure" delay={0.25} testId="pacing-v3-section"><div className="space-y-4">{(report.pacing_and_structure || []).map((item, index) => (
      <div key={index} className="pb-4 border-b border-ink-900/5 last:border-0"><div className="grid grid-cols-[5rem_1fr_4rem] gap-3 items-center"><a href={`/read/${manuscriptId}#section-${item.section}`} className="font-medium text-sm text-ink-700 hover:text-clay">Section {item.section}</a><div className="h-2.5 bg-ink-900/5 overflow-hidden" title={`${engagementStyles[item.engagement]?.label || "Mixed"} engagement`}><div className="h-full" style={{ width: (engagementStyles[item.engagement] || engagementStyles.mixed).width, backgroundColor: (engagementStyles[item.engagement] || engagementStyles.mixed).color }} /></div><span className="text-xs capitalize text-ink-500">{item.engagement}</span></div><p className="text-sm text-ink-600 mt-2">{item.diagnosis || "No specific pacing concern identified."}</p><EvidenceLinks items={item.evidence} manuscriptId={manuscriptId} /></div>
    ))}</div></Section>

    <Section icon={ListChecks} title="Revision plan" delay={0.3} testId="revision-plan-section" accent="#C86B56"><div className="space-y-6">{(report.revision_plan || []).map((item, index) => (
      <div key={index} className="pb-6 border-b border-ink-900/5 last:border-0"><div className="flex items-center gap-3 mb-2"><span className={`text-xs px-2 py-1 ${priorityStyles[item.priority] || priorityStyles.important}`}>{item.priority}</span><p className="font-medium text-ink-800">{item.action}</p></div><p className="text-sm text-ink-600"><span className="font-medium">Why:</span> {item.reason}</p><p className="text-sm text-ink-600 mt-1"><span className="font-medium">Expected impact:</span> {item.expected_impact}</p><EvidenceLinks items={item.evidence} manuscriptId={manuscriptId} /></div>
    ))}</div></Section>

    <Section icon={Wrench} title="Optional copy-edit appendix" delay={0.35} testId="copy-edit-section">
      {appendix ? <div><p className="text-sm text-ink-600 mb-5">{appendix.summary || "High-confidence mechanical findings only."}</p>{(appendix.items || []).length ? appendix.items.map((item, index) => (
        <div key={index} className="pb-5 mb-5 border-b border-ink-900/5 last:border-0"><div className="flex gap-2 items-center mb-2"><span className="chip">{item.category.replaceAll("_", " ")}</span><span className="text-xs text-ink-400">{Math.round(item.confidence * 100)}% confidence</span></div><p className="text-sm text-ink-600 line-through">{item.original}</p><p className="text-sm text-ink-800 mt-1">{item.suggestion}</p><p className="text-xs text-ink-500 mt-2">{item.explanation}</p><EvidenceLinks items={[{ paragraph_id: item.paragraph_id }]} manuscriptId={manuscriptId} /></div>
      )) : <p className="text-sm text-ink-500">No high-confidence mechanical issues found.</p>}</div> : <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4"><p className="text-sm text-ink-500 max-w-xl">Runs separately on a cheaper model and flags only high-confidence mechanical errors. It does not rewrite style or voice.</p><button onClick={onCopyEdit} disabled={copyEditing} className="flex items-center gap-2 bg-ink-900 text-white px-4 py-2 text-sm disabled:opacity-50">{copyEditing ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}{copyEditing ? "Checking..." : "Run copy edit"}</button></div>}
    </Section>
    {report.coverage?.partial && <p className="text-xs text-amber-700 mb-8">Partial coverage: {report.coverage.notes}</p>}
  </>;
}

function DidItLandContent({ didItLand }) {
  if (!didItLand) {
    return <p className="text-sm text-ink-400">No intent data collected from readers.</p>;
  }
  if (Array.isArray(didItLand)) {
    return (
      <div className="space-y-4">
        {didItLand.map((item, i) => (
          <div key={i} className="pb-4 border-b border-ink-900/5 last:border-0 last:pb-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs text-ink-400">Section {item.section}</span>
              {item.alignment && <span className="chip">{item.alignment}</span>}
            </div>
            <p className="text-sm text-ink-600 leading-relaxed">{item.summary}</p>
            {item.reader_intents && Object.keys(item.reader_intents).length > 0 && (
              <div className="mt-3 space-y-1">
                {Object.entries(item.reader_intents).map(([reader, intent]) => (
                  <p key={reader} className="text-xs text-ink-500"><span className="font-medium">{reader}:</span> {intent}</p>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }
  // Legacy reports stored this as a string.
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

function EngagementMapContent({ items }) {
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
            <span className="font-medium">{item.engagement_level || "unknown"}</span>
            {item.notes ? ` — ${item.notes}` : ""}
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
            {typeof item === "string" ? item : (
              <>
                <span className="font-medium">{item.topic}</span>
                {item.significance ? ` — ${item.significance}` : ""}
                {item.positions && Object.keys(item.positions).length > 0 && (
                  <span className="block mt-2 text-xs text-ink-500">
                    {Object.entries(item.positions).map(([reader, position]) => `${reader}: ${position}`).join(" · ")}
                  </span>
                )}
              </>
            )}
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
        const askedBy = typeof item === "object" && Array.isArray(item.asked_by) ? item.asked_by : [];
        const multiple = typeof item === "object" ? (item.asked_by_multiple || askedBy.length > 1) : false;
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
              {askedBy.length > 0 && <p className="text-xs text-ink-400 mt-1">{askedBy.join(", ")}</p>}
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
            {item.comment || item.quote_or_summary}
          </p>
          {item.why_selected && <p className="text-xs text-ink-400 mt-2">{item.why_selected}</p>}
        </div>
      ))}
    </div>
  );
}

function StoryOverviewContent({ overview }) {
  return (
    <div className="space-y-3">
      {overview.premise && <p className="text-base text-ink-700 leading-relaxed">{overview.premise}</p>}
      <div className="flex flex-wrap gap-2 text-xs text-ink-500">
        {overview.genre && <span className="chip">{overview.genre}</span>}
        {overview.tone && <span className="chip">{overview.tone}</span>}
      </div>
    </div>
  );
}

function CharacterPerceptionContent({ items }) {
  return <div className="space-y-4">{items.map((item, i) => (
    <div key={i} className="pb-4 border-b border-ink-900/5 last:border-0">
      <p className="font-medium text-sm text-ink-700">{item.character}</p>
      {item.consensus_or_split && <p className="text-sm text-ink-600 mt-1">{item.consensus_or_split}</p>}
      {item.reader_impressions && <div className="mt-2 space-y-1">{Object.entries(item.reader_impressions).map(([reader, impression]) => (
        <p key={reader} className="text-xs text-ink-500"><span className="font-medium">{reader}:</span> {impression}</p>
      ))}</div>}
    </div>
  ))}</div>;
}

function PredictionTrackerContent({ items }) {
  return <div className="space-y-3">{items.map((item, i) => (
    <div key={i} className="text-sm text-ink-600">
      <span className="font-medium">{item.reader}:</span> {item.prediction}
      {item.outcome && <span className="chip ml-2">{item.outcome}</span>}
    </div>
  ))}</div>;
}

function ConsensusContent({ items }) {
  return <div className="space-y-3">{items.map((item, i) => (
    <div key={i} className="pb-3 border-b border-ink-900/5 last:border-0">
      <p className="text-sm text-ink-700">Section {item.section}{item.paragraph ? `, paragraph ${item.paragraph}` : ""}: {item.what_happened}</p>
      {item.significance && <p className="text-xs text-ink-500 mt-1">{item.significance}</p>}
    </div>
  ))}</div>;
}
