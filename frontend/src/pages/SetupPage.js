import ReaderAvatar from "../components/ReaderAvatar";
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import SiteHeader from "../components/SiteHeader";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { Upload, FileText, ChevronRight, RefreshCw, X, Plus, BookOpen, Trash2, SlidersHorizontal, Save } from "lucide-react";
import axios from "axios";
import { getApi } from "../apiConfig";
import { manuscriptRequestConfig } from "../manuscriptAccess";

const API = getApi();

// Chunked upload: if request body would exceed this (bytes), send in chunks to avoid 413.
// Use a conservative 90KB so we stay under typical proxy/h11 limits (~1MB or 16KB); backend allows 100MB.
const SAFE_BODY_SIZE = 90 * 1024; // 90KB
const CHUNK_CHARS = 80 * 1024; // 80K chars per chunk (~80KB per request)

const STEPS = ["manuscript", "genre", "readers"];


const PERSONALITY_COLORS = {
  analytical: "#66616A",
  emotional: "#493449",
  casual: "#526653",
  skeptical: "#94712D",
  genre_savvy: "#302D32",
};

// One-line reading style per archetype (matches backend READER_ARCHETYPES order)
const ARCHETYPE_DESCRIPTIONS = {
  emotional: "Reads for emotional connection",
  analytical: "Focuses on plot and structure",
  skeptical: "Questions everything",
  genre_savvy: "Deeply familiar with genre",
  casual: "Reads for entertainment",
};
const MAX_READERS = 5;
const FALLBACK_FOCUS_GROUPS = [
  { group: "Character", options: [
    ["emotional_authenticity", "Emotional authenticity"], ["character_motivation", "Character motivation"],
    ["relationship_chemistry", "Relationship chemistry"], ["character_growth", "Character growth"], ["dialogue", "Dialogue"],
  ].map(([id, label]) => ({ id, label })) },
  { group: "Story", options: [
    ["pacing_momentum", "Pacing and momentum"], ["plot_logic", "Plot logic"], ["continuity", "Continuity"],
    ["tension_suspense", "Tension and suspense"], ["setup_payoff", "Setup and payoff"], ["mystery_clues", "Mystery clues"],
  ].map(([id, label]) => ({ id, label })) },
  { group: "Craft", options: [
    ["prose_voice", "Prose and voice"], ["exposition_clarity", "Exposition clarity"],
    ["viewpoint", "Viewpoint"], ["worldbuilding", "Worldbuilding"],
  ].map(([id, label]) => ({ id, label })) },
  { group: "Reader experience", options: [
    ["immersion", "Immersion"], ["predictability", "Predictability"],
    ["genre_expectations", "Genre expectations"], ["thematic_subtext", "Thematic subtext"],
  ].map(([id, label]) => ({ id, label })) },
];

function getReaderDisplayName(p, index) {
  const n = p?.name;
  if (n != null && String(n).trim()) return String(n).trim();
  return `Reader ${(index ?? p?.avatar_index ?? 0) + 1}`;
}

export default function SetupPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState("manuscript");
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [manuscript, setManuscript] = useState(null);
  const [genre, setGenre] = useState({});
  const [model, setModel] = useState("gemini-2.5-flash");
  const [pipelineConfig, setPipelineConfig] = useState(null);
  const [comparableInput, setComparableInput] = useState("");
  const [personas, setPersonas] = useState([]);
  const [selectedReaderIds, setSelectedReaderIds] = useState([]);
  const [costEstimate, setCostEstimate] = useState(null);
  const [regeneratingId, setRegeneratingId] = useState(null);
  const [editingReaderId, setEditingReaderId] = useState(null);
  const [readerDraft, setReaderDraft] = useState(null);
  const [savingReaderFocus, setSavingReaderFocus] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const [uploadedFileName, setUploadedFileName] = useState(null);

  useEffect(() => {
    axios.get(`${API}/config/models`)
      .then((res) => setPipelineConfig(res.data))
      .catch(() => setPipelineConfig(null));
  }, []);

  const handleFileUpload = async (file) => {
    if (!file) return;
    const name = file.name || "";
    if (!name.endsWith(".txt") && !name.endsWith(".docx") && !name.endsWith(".pdf")) {
      toast.error("Please upload a .txt, .docx, or .pdf file");
      return;
    }
    if (name.endsWith(".docx") || name.endsWith(".pdf")) {
      // For .docx and .pdf, upload to backend for extraction
      setLoading(true);
      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("title", title || name.replace(/\.(docx|pdf)$/, ""));
        const res = await axios.post(`${API}/manuscripts/upload`, formData, { withCredentials: true });
        // docx/pdf upload goes straight to the manuscript — skip text paste step
        setManuscript(res.data);
        setGenre({
          genre: res.data.genre,
          target_audience: res.data.target_audience,
          age_range: res.data.age_range,
          comparable_books: res.data.comparable_books || [],
        });
        setModel(res.data.model || "gemini-2.5-flash");
        setUploadedFileName(name);
        setTitle((t) => t || name.replace(/\.(docx|pdf)$/, ""));
        setStep("genre");
        toast.success(`Extracted text from ${name}`);
      } catch (err) {
        toast.error(err?.response?.data?.detail?.message || err?.response?.data?.detail || "Could not upload manuscript");
      } finally {
        setLoading(false);
      }
      return;
    }
    // .txt — read locally
    const fileText = await file.text();
    setText(fileText);
    setUploadedFileName(name);
    if (!title) setTitle(name.replace(".txt", ""));
    toast.success("File loaded successfully");
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    handleFileUpload(file);
  };

  const submitManuscript = async () => {
    if (!text.trim() || text.trim().length < 100) {
      toast.error("Please paste a manuscript with at least 100 characters");
      return;
    }
    setLoading(true);
    try {
      const payload = { title: title || "Untitled Manuscript", raw_text: text, model: model };
      const payloadStr = JSON.stringify(payload);
      // Use byte length (UTF-8), not string length — so we compare bytes to bytes
      const bodySizeBytes = new TextEncoder().encode(payloadStr).length;

      let res;
      if (bodySizeBytes <= SAFE_BODY_SIZE) {
        res = await axios.post(`${API}/manuscripts`, payload, { withCredentials: true });
      } else {
        // Chunked upload to avoid 413 (proxy body limit)
        const firstChunk = text.slice(0, CHUNK_CHARS);
        res = await axios.post(`${API}/manuscripts`, {
          title: title || "Untitled Manuscript",
          raw_text: firstChunk,
          model: model,
        }, { withCredentials: true });
        const manuscriptId = res?.data?.id;
        if (!manuscriptId) {
          throw new Error("Server did not return a manuscript id. Cannot append remaining text.");
        }
        for (let start = CHUNK_CHARS; start < text.length; start += CHUNK_CHARS) {
          const chunk = text.slice(start, start + CHUNK_CHARS);
          res = await axios.patch(
            `${API}/manuscripts/${manuscriptId}/append-text`,
            { raw_text_chunk: chunk },
            manuscriptRequestConfig(manuscriptId)
          );
        }
      }
      setManuscript(res.data);
      setGenre({
        genre: res.data.genre,
        target_audience: res.data.target_audience,
        age_range: res.data.age_range,
        comparable_books: res.data.comparable_books || [],
      });
      setModel(res.data.model || "gemini-2.5-flash");
      setStep("genre");
    } catch (err) {
      const status = err.response?.status;
      const data = err.response?.data;
      const payloadStr = JSON.stringify({ title: title || "Untitled Manuscript", raw_text: text });
      const bodySizeBytes = new TextEncoder().encode(payloadStr).length;
      const sizeMB = (bodySizeBytes / (1024 * 1024)).toFixed(2);
      let msg;
      if (status === 404) {
        msg = "We couldn’t process this manuscript. Please try again shortly.";
      } else if (status === 413) {
        msg = bodySizeBytes <= SAFE_BODY_SIZE
          ? `Server rejected the request (413). Your manuscript is ${sizeMB} MB, under the 100 MB limit — the server may need a higher upload limit.`
          : "Manuscript is too large for the server limit (max 100 MB).";
      } else {
        msg = err.response?.data?.detail ?? err.response?.data?.message ?? err.message ?? "Failed to process manuscript. Please try again.";
      }
      if (err.message === "Network Error" || !err.response) {
        msg = "We couldn’t connect. Check your connection and try again; your pasted text is still here.";
      }
      const msgText = Array.isArray(msg) ? msg.map((m) => m.msg ?? m).join(", ") : msg;
      toast.error(msgText);
    } finally {
      setLoading(false);
    }
  };

  const saveGenreAndProceed = async () => {
    setLoading(true);
    try {
      await axios.patch(`${API}/manuscripts/${manuscript.id}/genre`, { ...genre, model }, manuscriptRequestConfig(manuscript.id));
      // Generate personas — can take 20-40s for 5 parallel LLM calls
      const res = await axios.get(`${API}/manuscripts/${manuscript.id}/personas`, manuscriptRequestConfig(manuscript.id, { timeout: 120000 }));
      if (!res.data || res.data.length === 0) {
        throw new Error("No personas returned");
      }
      setPersonas(res.data);
      setSelectedReaderIds(res.data.map((p) => p.id));
      setStep("readers");
    } catch (err) {
      const detail = err.response?.data?.detail ?? err.response?.data?.message;
      const msg = typeof detail === "string" ? detail : (Array.isArray(detail) ? detail.map((d) => d.msg ?? d).join(", ") : null);
      toast.error(msg || err.message || "Reader generation timed out or failed. Please try again.");
      setLoading(false);
    } finally {
      setLoading(false);
    }
  };

  const regenerateReader = async (readerId) => {
    setRegeneratingId(readerId);
    try {
      const res = await axios.post(`${API}/manuscripts/${manuscript.id}/personas/regenerate`, {
        reader_id: readerId,
      }, manuscriptRequestConfig(manuscript.id));
      setPersonas((prev) => prev.map((p) => (p.id === readerId ? res.data : p)));
      if (editingReaderId === readerId) {
        setEditingReaderId(null);
        setReaderDraft(null);
      }
      toast.success("Reader regenerated");
    } catch (err) {
      toast.error("Failed to regenerate reader");
    } finally {
      setRegeneratingId(null);
    }
  };

  const regenerateAll = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${API}/manuscripts/${manuscript.id}/personas/regenerate`, {}, manuscriptRequestConfig(manuscript.id));
      setPersonas(res.data);
      setSelectedReaderIds(res.data.map((p) => p.id));
      toast.success("All readers regenerated");
    } catch (err) {
      toast.error("Failed to regenerate readers");
    } finally {
      setLoading(false);
    }
  };

  const addReader = async () => {
    if (selectedReaderIds.length >= MAX_READERS) return;
    setLoading(true);
    try {
      const res = await axios.post(`${API}/manuscripts/${manuscript.id}/personas/add`, {}, manuscriptRequestConfig(manuscript.id));
      const newPersona = res.data;
      setPersonas((prev) => [...prev, newPersona]);
      setSelectedReaderIds((prev) => [...prev, newPersona.id]);
      toast.success(`${getReaderDisplayName(newPersona)} added to the panel`);
    } catch (err) {
      const msg = err.response?.data?.detail ?? err.response?.data?.message ?? err.message;
      toast.error(typeof msg === "string" ? msg : msg?.message || "Failed to add reader");
    } finally {
      setLoading(false);
    }
  };

  const removeReader = (readerId) => {
    if (selectedReaderIds.length <= 1) return;
    setSelectedReaderIds((prev) => prev.filter((id) => id !== readerId));
    if (editingReaderId === readerId) {
      setEditingReaderId(null);
      setReaderDraft(null);
    }
  };

  const focusGroups = pipelineConfig?.reader_focus_options || FALLBACK_FOCUS_GROUPS;
  const focusLabel = (focusId) => focusGroups.flatMap((group) => group.options).find((option) => option.id === focusId)?.label || focusId;
  const selectedPrimaryCounts = personas
    .filter((reader) => selectedReaderIds.includes(reader.id) && reader.primary_focus)
    .reduce((counts, reader) => ({ ...counts, [reader.primary_focus]: (counts[reader.primary_focus] || 0) + 1 }), {});
  const repeatedPrimaryFocuses = Object.entries(selectedPrimaryCounts).filter(([, count]) => count > 1).map(([focus]) => focusLabel(focus));

  const openReaderCustomization = (reader) => {
    if (editingReaderId === reader.id) {
      setEditingReaderId(null);
      setReaderDraft(null);
      return;
    }
    setEditingReaderId(reader.id);
    setReaderDraft({
      primary_focus: reader.primary_focus || "",
      secondary_focuses: [...(reader.secondary_focuses || [])],
      writer_focus_note: reader.writer_focus_note || "",
      liked_tropes: [...(reader.liked_tropes || [])],
      disliked_tropes: [...(reader.disliked_tropes || [])],
    });
  };

  const toggleSecondaryFocus = (focusId) => {
    setReaderDraft((current) => {
      if (!current || focusId === current.primary_focus) return current;
      const selected = current.secondary_focuses || [];
      if (selected.includes(focusId)) return { ...current, secondary_focuses: selected.filter((item) => item !== focusId) };
      if (selected.length >= 2) return current;
      return { ...current, secondary_focuses: [...selected, focusId] };
    });
  };

  const removeDraftTaste = (field, value) => {
    setReaderDraft((current) => ({ ...current, [field]: current[field].filter((item) => item !== value) }));
  };

  const saveReaderCustomization = async () => {
    if (!editingReaderId || !readerDraft) return;
    setSavingReaderFocus(true);
    try {
      const payload = {
        ...readerDraft,
        primary_focus: readerDraft.primary_focus || null,
        secondary_focuses: readerDraft.secondary_focuses.filter((item) => item !== readerDraft.primary_focus),
      };
      const res = await axios.patch(
        `${API}/manuscripts/${manuscript.id}/personas/${editingReaderId}/focus`,
        payload,
        manuscriptRequestConfig(manuscript.id)
      );
      setPersonas((current) => current.map((reader) => reader.id === editingReaderId ? res.data : reader));
      setEditingReaderId(null);
      setReaderDraft(null);
      toast.success("Reader focus saved");
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Could not save reader focus");
    } finally {
      setSavingReaderFocus(false);
    }
  };

  useEffect(() => {
    if (!manuscript?.id || step !== "readers" || selectedReaderIds.length === 0) return;
    const timer = window.setTimeout(async () => {
      try {
        const ids = encodeURIComponent(selectedReaderIds.join(","));
        const res = await axios.get(`${API}/manuscripts/${manuscript.id}/cost-estimate?operation=remaining&reader_ids=${ids}`, manuscriptRequestConfig(manuscript.id));
        setCostEstimate(res.data);
      } catch (err) {
        setCostEstimate(null);
        toast.error("Could not estimate credits. Please try selecting your readers again.");
      }
    }, 350);
    return () => window.clearTimeout(timer);
  }, [manuscript?.id, step, selectedReaderIds]);

  const startReading = async () => {
    try {
      if (!costEstimate || !costEstimate.can_start) { toast.error("Check your available credits before starting."); return; }
      navigate(`/read/${manuscript.id}`, { state: { selectedReaderIds } });
    } catch (err) {
      toast.error(err.response?.data?.detail?.message || err.response?.data?.detail || "Could not start reading");
    }
  };

  const addComparable = () => {
    if (comparableInput.trim()) {
      setGenre((g) => ({ ...g, comparable_books: [...(g.comparable_books || []), comparableInput.trim()] }));
      setComparableInput("");
    }
  };

  const removeComparable = (idx) => {
    setGenre((g) => ({ ...g, comparable_books: g.comparable_books.filter((_, i) => i !== idx) }));
  };

  const stepIndex = STEPS.indexOf(step);

  return (
    <div className="min-h-screen bg-paper setup-page">
      <SiteHeader />
      <nav className="setup-steps" aria-label="Manuscript setup progress"><ol>{["Manuscript", "Genre & audience", "Your readers"].map((label, i) => <li key={label} aria-current={i === stepIndex ? "step" : undefined}><span>{i < stepIndex ? "✓" : i + 1}</span><span>{label}</span></li>)}</ol></nav>
      <main id="main-content" className="setup-content" tabIndex={-1}>
        <AnimatePresence mode="wait">
          {/* ── Limit reached card ── */}
          {step === "manuscript" && (
            <motion.div
              key="manuscript"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.35 }}
            >
              <div className="mb-8">
                <h2 className="font-serif text-4xl text-ink-900 mb-3" style={{ fontFamily: "'Instrument Serif', serif" }}>
                  Bring your manuscript to the table
                </h2>
                <p className="text-ink-600 text-base">
                  A chapter, a short story, or the whole draft. Bring your words, then choose the readers you’d like to hear from.
                </p>
              </div>

              <div className="manuscript-upload"><div>
              <div className="mb-4">
                <label htmlFor="manuscript-title" className="block text-sm mb-2 text-ink-600">Title <span className="text-ink-400">(optional)</span></label>
                <input id="manuscript-title"
                  data-testid="manuscript-title-input"
                  type="text"
                  placeholder="Manuscript title (optional)"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full border border-ink-900/12 bg-white px-4 py-3 text-sm text-ink-900 placeholder:text-ink-400 focus:outline-none focus:border-clay transition-colors"
                  style={{ borderRadius: "2px" }}
                />
              </div>

              <label htmlFor="manuscript-text" className="block text-sm mb-2 text-ink-600">Your manuscript</label>
              {/* Drop zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                className={`relative border-2 border-dashed transition-all duration-200 mb-4 ${
                  dragOver ? "border-clay bg-clay/5" : "border-ink-900/15 bg-white"
                }`}
                style={{ borderRadius: "2px" }}
              >
                <textarea id="manuscript-text"
                  data-testid="manuscript-text-area"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Paste your manuscript here... or drag and drop a .txt, .docx, or .pdf file above"
                  className="w-full h-80 bg-transparent border-none focus:outline-none focus:ring-0 p-6 manuscript-text resize-none placeholder:text-ink-400"
                  style={{ fontFamily: 'Georgia, serif', fontSize: '1rem', lineHeight: '1.85' }}
                />
                {dragOver && (
                  <div className="absolute inset-0 flex items-center justify-center bg-paper/80 pointer-events-none">
                    <div className="text-center">
                      <Upload className="w-8 h-8 text-clay mx-auto mb-2" strokeWidth={1.5} />
                      <p className="text-clay font-medium">Drop your .txt, .docx, or .pdf file</p>
                    </div>
                  </div>
                )}
              </div>

              <div className="upload-actions">
                <label
                  data-testid="file-upload-label"
                  className="upload-file-control flex items-center gap-2 text-sm text-ink-600 cursor-pointer hover:text-clay transition-colors"
                >
                  <Upload className="w-4 h-4" strokeWidth={1.5} />
                  {uploadedFileName ? (
                    <span className="text-clay font-medium truncate max-w-xs" data-testid="uploaded-filename">{uploadedFileName}</span>
                  ) : (
                    "Choose a file"
                  )}
                  <input
                    type="file"
                    accept=".txt,.docx,.pdf"
                    className="sr-only"
                    disabled={loading}
                    onChange={(e) => handleFileUpload(e.target.files[0])}
                    data-testid="file-upload-input"
                  />
                </label>

                <div className="flex items-center gap-3">
                  {text && (
                    <span className="text-xs text-ink-400">
                      {text.split(/\s+/).filter(Boolean).length.toLocaleString()} words
                    </span>
                  )}
                  <button
                    data-testid="submit-manuscript-btn"
                    onClick={submitManuscript}
                    disabled={loading || !text.trim()}
                    className="flex items-center gap-2 bg-clay hover:bg-clay-hover text-white px-6 py-3 text-sm font-medium transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{ borderRadius: "2px" }}
                  >
                    {loading ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" strokeWidth={1.5} />
                        Analyzing...
                      </>
                    ) : (
                      <>
                        Continue
                        <ChevronRight className="w-4 h-4" strokeWidth={1.5} />
                      </>
                    )}
                  </button>
                </div>
              </div>
              </div><aside className="upload-notes"><h3>Before we begin</h3><p>Upload a TXT, DOCX, or PDF, or paste your writing directly. You can start with an excerpt of at least 100 characters.</p><p>Next, you’ll confirm the genre and shape your panel of up to five AI readers.</p><p>AI analysis and reader setup use credits. You’ll see an estimate before the full reading. <Link to="/billing">View your credits</Link></p></aside></div>
            </motion.div>
          )}

          {/* ── Step 2: Genre & Audience ── */}
          {step === "genre" && (
            <motion.div
              key="genre"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.35 }}
            >
              <div className="mb-8">
                <h2 className="font-serif text-4xl text-ink-900 mb-3" style={{ fontFamily: "'Instrument Serif', serif" }}>
                  Your story's identity
                </h2>
                <p className="text-ink-600 text-base">
                  We've auto-detected these details. Edit them if needed — your readers will be tailored to match.
                </p>
              </div>

              <div className="bg-white border border-ink-900/8 p-8 space-y-6" style={{ borderRadius: "2px" }}>
                {/* Genre */}
                <div>
                  <label htmlFor="genre-input" className="text-xs text-ink-400 uppercase tracking-widest block mb-2">Genre</label>
                  <input
                    id="genre-input" data-testid="genre-input"
                    value={genre.genre || ""}
                    onChange={(e) => setGenre((g) => ({ ...g, genre: e.target.value }))}
                    className="w-full border border-ink-900/12 px-4 py-2.5 text-sm text-ink-900 focus:outline-none focus:border-clay transition-colors bg-paper"
                    style={{ borderRadius: "2px" }}
                  />
                </div>

                {/* Target Audience */}
                <div>
                  <label htmlFor="audience-input" className="text-xs text-ink-400 uppercase tracking-widest block mb-2">Target audience</label>
                  <input
                    id="audience-input" data-testid="audience-input"
                    value={genre.target_audience || ""}
                    onChange={(e) => setGenre((g) => ({ ...g, target_audience: e.target.value }))}
                    className="w-full border border-ink-900/12 px-4 py-2.5 text-sm text-ink-900 focus:outline-none focus:border-clay transition-colors bg-paper"
                    style={{ borderRadius: "2px" }}
                  />
                </div>

                {/* Age Range */}
                <div>
                  <label className="text-xs text-ink-400 uppercase tracking-widest block mb-2">Age Range</label>
                  <div className="flex gap-2 flex-wrap">
                    {["Middle Grade", "YA", "New Adult", "Adult"].map((range) => (
                      <button
                        key={range}
                        data-testid={`age-range-${range.replace(/\s+/g, "-").toLowerCase()}`}
                        aria-pressed={genre.age_range === range}
                        onClick={() => setGenre((g) => ({ ...g, age_range: range }))}
                        className={`chip cursor-pointer transition-all ${genre.age_range === range ? "border-clay text-clay bg-clay/5" : ""}`}
                      >
                        {range}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Comparable Books */}
                <div>
                  <label className="text-xs text-ink-400 uppercase tracking-widest block mb-2">Comparable Books</label>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {(genre.comparable_books || []).map((book, i) => (
                      <span key={i} className="chip group">
                        {book}
                        <button onClick={() => removeComparable(i)} className="ml-1 text-ink-400 hover:text-clay">
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      aria-label="Comparable book" data-testid="comparable-book-input"
                      value={comparableInput}
                      onChange={(e) => setComparableInput(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && addComparable()}
                      placeholder="Add a comparable book..."
                      className="flex-1 border border-ink-900/12 px-3 py-2 text-sm focus:outline-none focus:border-clay transition-colors bg-paper"
                      style={{ borderRadius: "2px" }}
                    />
                    <button
                      aria-label="Add comparable book" data-testid="add-comparable-btn"
                      onClick={addComparable}
                      className="px-3 py-2 border border-ink-900/12 hover:border-clay text-ink-600 hover:text-clay transition-colors"
                      style={{ borderRadius: "2px" }}
                    >
                      <Plus className="w-4 h-4" strokeWidth={1.5} />
                    </button>
                  </div>
                </div>

                {/* Reader model — this value is stored on the manuscript and
                    directly controls every reader call. */}
                <div>
                  <label className="text-xs text-ink-400 uppercase tracking-widest block mb-2">Reader quality</label>
                  {pipelineConfig?.pipeline_version === "v2" ? (
                    <div className="border border-sage/30 bg-sage/5 p-4" style={{ borderRadius: "2px" }}>
                      <span className="block text-sm font-medium text-ink-900">A continuous, attentive reading</span>
                      <span className="block text-xs text-ink-500 mt-1">
                        Your readers follow the story in sequence, tracking their questions and impressions as they go.
                      </span>
                    </div>
                  ) : (
                  <div className="grid sm:grid-cols-2 gap-3">
                    {[
                      {
                        value: "gemini-2.5-flash",
                        label: "Standard",
                        detail: "Gemini 2.5 Flash · faster and lower cost",
                      },
                      {
                        value: "gemini-2.5-pro",
                        label: "Deep reading",
                        detail: "Gemini 2.5 Pro · slower and more expensive",
                      },
                    ].map((option) => (
                      <button
                        type="button"
                        key={option.value}
                        data-testid={`reader-model-${option.value}`}
                        onClick={() => setModel(option.value)}
                        className={`text-left border p-3 transition-colors ${
                          model === option.value
                            ? "border-clay bg-clay/5"
                            : "border-ink-900/10 hover:border-ink-900/25"
                        }`}
                        style={{ borderRadius: "2px" }}
                      >
                        <span className="block text-sm font-medium text-ink-900">{option.label}</span>
                        <span className="block text-xs text-ink-400 mt-1">{option.detail}</span>
                      </button>
                    ))}
                  </div>
                  )}
                  <p className="text-xs text-ink-400 mt-2">You’ll see a credit estimate after choosing your readers.</p>
                </div>

                {/* Sections detected */}
                {manuscript && (
                  <div className="pt-2 border-t border-ink-900/8 flex items-center gap-3 text-sm text-ink-600">
                    <BookOpen className="w-4 h-4 text-ink-400" strokeWidth={1.5} />
                    <span>
                      Detected{" "}
                      <strong className="text-ink-900">{manuscript.total_sections}</strong>{" "}
                      {manuscript.total_sections === 1 ? "section" : "sections"} in your manuscript
                    </span>
                  </div>
                )}
              </div>

              <div className="flex justify-between mt-6">
                <button
                  data-testid="back-to-manuscript-btn"
                  onClick={() => setStep("manuscript")}
                  className="text-sm text-ink-600 hover:text-ink-900 transition-colors"
                >
                  ← Back
                </button>
                <button
                  data-testid="proceed-to-readers-btn"
                  onClick={saveGenreAndProceed}
                  disabled={loading}
                  className="flex items-center gap-2 bg-clay hover:bg-clay-hover text-white px-6 py-3 text-sm font-medium transition-all duration-200 disabled:opacity-40"
                  style={{ borderRadius: "2px" }}
                >
                  {loading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" strokeWidth={1.5} />
                      Assembling readers...
                    </>
                  ) : (
                    <>
                      Meet your readers
                      <ChevronRight className="w-4 h-4" strokeWidth={1.5} />
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          )}

          {/* ── Step 3: Readers ── */}
          {step === "readers" && (
            <motion.div
              key="readers"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.35 }}
            >
              <div className="mb-8 flex items-start justify-between">
                <div>
                  <h2 className="font-serif text-4xl text-ink-900 mb-3" style={{ fontFamily: "'Instrument Serif', serif" }}>
                    Your reading panel
                  </h2>
                  <p className="text-ink-600 text-base">
                    Choose 1–5 readers. Each brings a different perspective. Regenerate any you'd like to change.
                  </p>
                </div>
                <button
                  data-testid="regenerate-all-btn"
                  onClick={regenerateAll}
                  disabled={loading}
                  className="flex items-center gap-2 text-sm text-ink-600 hover:text-clay border border-ink-900/12 hover:border-clay px-4 py-2 transition-all duration-200"
                  style={{ borderRadius: "2px" }}
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} strokeWidth={1.5} />
                  Regenerate all
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-6">
                <AnimatePresence mode="popLayout">
                  {personas
                    .filter((p) => selectedReaderIds.includes(p.id))
                    .sort((a, b) => selectedReaderIds.indexOf(a.id) - selectedReaderIds.indexOf(b.id))
                    .map((p, i) => (
                      <motion.div
                        key={p.id}
                        layout
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                        transition={{ duration: 0.25 }}
                        data-testid={`reader-card-${i}`}
                        className="bg-white border border-ink-900/8 p-6 relative group hover:shadow-md transition-all duration-300"
                        style={{ borderRadius: "2px" }}
                      >
                        {selectedReaderIds.length > 1 && (
                          <button
                            type="button"
                            data-testid={`remove-reader-${p.id}`}
                            onClick={() => removeReader(p.id)}
                            className="absolute top-4 right-4 text-ink-400 hover:text-clay transition-colors"
                            aria-label={`Remove ${getReaderDisplayName(p, i)}`}
                          >
                            <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                          </button>
                        )}
                        <button
                          data-testid={`regen-reader-${i}`}
                          onClick={() => regenerateReader(p.id)}
                          disabled={regeneratingId === p.id}
                          className="absolute top-4 right-4 opacity-100 transition-opacity text-ink-400 hover:text-clay flex items-center gap-1"
                          style={selectedReaderIds.length > 1 ? { right: "2.5rem" } : {}}
                          aria-label="Regenerate this reader"
                        >
                          <RefreshCw
                            className={`w-3.5 h-3.5 ${regeneratingId === p.id ? "animate-spin" : ""}`}
                            strokeWidth={1.5}
                          />
                        </button>

                        <div className="flex items-start gap-3 mb-3">
                          <div className="w-12 h-12 overflow-hidden flex-shrink-0" style={{ borderRadius: "2px" }}>
                            <ReaderAvatar name={getReaderDisplayName(p, i)} index={p.avatar_index} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <h3 className="font-medium text-ink-900 text-base">{getReaderDisplayName(p, i)}</h3>
                            <p className="text-xs text-ink-500">
                              {ARCHETYPE_DESCRIPTIONS[p.personality] || p.personality}
                            </p>
                            <p className="text-xs text-ink-400 mt-0.5">{p.age} · {p.occupation}</p>
                          </div>
                        </div>

                        <div className="mb-3">
                          <span
                            className="text-xs uppercase tracking-widest font-semibold px-2 py-1"
                            style={{
                              color: PERSONALITY_COLORS[p.personality] || "#66616A",
                              backgroundColor: `${PERSONALITY_COLORS[p.personality] || "#66616A"}15`,
                              borderRadius: "2px",
                            }}
                          >
                            {p.personality}
                          </span>
                        </div>

                        <p className="text-xs text-ink-600 mb-3 leading-relaxed">{p.reading_habits}</p>

                        <blockquote
                          className="text-sm text-ink-600 border-l-2 border-clay pl-3 mt-3"
                          style={{ fontFamily: "'Instrument Serif', serif", fontStyle: "italic", fontSize: "0.95rem" }}
                        >
                          "{p.quote}"
                        </blockquote>

                        <div className="mt-4 pt-3 border-t border-ink-900/6">
                          <p className="text-[10px] uppercase tracking-widest text-ink-400 mb-2">Personal tastes</p>
                          <div className="flex flex-wrap gap-1">
                            {(p.liked_tropes || []).slice(0, 2).map((t, ti) => (
                              <span key={ti} className="text-xs text-sage bg-sage/10 px-2 py-0.5" style={{ borderRadius: "2px" }}>
                                + {t}
                              </span>
                            ))}
                            {(p.disliked_tropes || []).slice(0, 1).map((t, ti) => (
                              <span key={ti} className="text-xs text-clay/80 bg-clay/10 px-2 py-0.5" style={{ borderRadius: "2px" }}>
                                − {t}
                              </span>
                            ))}
                          </div>
                        </div>

                        {(p.primary_focus || (p.secondary_focuses || []).length > 0) && (
                          <div className="mt-3">
                            <p className="text-[10px] uppercase tracking-widest text-ink-400 mb-1.5">Your assignment</p>
                            <div className="flex flex-wrap gap-1">
                              {p.primary_focus && <span className="text-xs text-clay bg-clay/10 px-2 py-0.5">Primary · {focusLabel(p.primary_focus)}</span>}
                              {(p.secondary_focuses || []).map((focus) => <span key={focus} className="text-xs text-ink-500 bg-ink-900/5 px-2 py-0.5">{focusLabel(focus)}</span>)}
                            </div>
                          </div>
                        )}

                        <button
                          type="button"
                          onClick={() => openReaderCustomization(p)}
                          className={`mt-4 w-full flex items-center justify-center gap-2 border px-3 py-2 text-xs transition-colors ${editingReaderId === p.id ? "border-clay text-clay bg-clay/5" : "border-ink-900/10 text-ink-500 hover:border-clay hover:text-clay"}`}
                          data-testid={`customize-reader-${p.id}`}
                        >
                          <SlidersHorizontal className="w-3.5 h-3.5" />
                          {p.primary_focus || p.writer_focus_note ? "Edit focus" : "Customize focus"}
                        </button>
                      </motion.div>
                    ))}
                </AnimatePresence>
              </div>

              {editingReaderId && readerDraft && (() => {
                const reader = personas.find((item) => item.id === editingReaderId);
                if (!reader) return null;
                return (
                  <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-8 bg-white border border-clay/25 p-6" data-testid="reader-focus-editor">
                    <div className="flex items-start justify-between gap-4 mb-6">
                      <div>
                        <p className="text-xs uppercase tracking-widest text-clay">Light customization</p>
                        <h3 className="font-serif text-2xl text-ink-900 mt-1" style={{ fontFamily: "'Instrument Serif', serif" }}>Guide what {getReaderDisplayName(reader)} watches</h3>
                        <p className="text-xs text-ink-500 mt-1">Focus changes attention, not opinion. Nothing here requires a comment.</p>
                      </div>
                      <button onClick={() => { setEditingReaderId(null); setReaderDraft(null); }} aria-label="Close reader customization"><X className="w-4 h-4 text-ink-400" /></button>
                    </div>

                    <div className="grid md:grid-cols-2 gap-7">
                      <div>
                        <label className="text-xs uppercase tracking-widest text-ink-400 block mb-2">Primary focus</label>
                        <select
                          value={readerDraft.primary_focus}
                          onChange={(event) => setReaderDraft((current) => ({
                            ...current,
                            primary_focus: event.target.value,
                            secondary_focuses: current.secondary_focuses.filter((item) => item !== event.target.value),
                          }))}
                          className="w-full border border-ink-900/12 bg-paper px-3 py-2.5 text-sm text-ink-700 focus:outline-none focus:border-clay"
                        >
                          <option value="">Use only their natural tendencies</option>
                          {focusGroups.map((group) => <optgroup key={group.group} label={group.group}>{group.options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}</optgroup>)}
                        </select>

                        <p className="text-xs uppercase tracking-widest text-ink-400 mt-5 mb-2">Secondary interests <span className="normal-case tracking-normal">({readerDraft.secondary_focuses.length}/2)</span></p>
                        <div className="space-y-3 max-h-56 overflow-y-auto pr-2">
                          {focusGroups.map((group) => (
                            <div key={group.group}>
                              <p className="text-[10px] uppercase tracking-widest text-ink-400 mb-1.5">{group.group}</p>
                              <div className="flex flex-wrap gap-1.5">
                                {group.options.map((option) => {
                                  const selected = readerDraft.secondary_focuses.includes(option.id);
                                  const disabled = option.id === readerDraft.primary_focus || (!selected && readerDraft.secondary_focuses.length >= 2);
                                  return <button key={option.id} type="button" disabled={disabled} onClick={() => toggleSecondaryFocus(option.id)} className={`text-xs border px-2 py-1.5 transition-colors disabled:opacity-30 ${selected ? "border-clay text-clay bg-clay/5" : "border-ink-900/10 text-ink-500 hover:border-clay"}`}>{option.label}</button>;
                                })}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div>
                        <p className="text-xs uppercase tracking-widest text-ink-400 mb-2">Personal tastes</p>
                        <p className="text-xs text-ink-500 mb-3">Generated parts of this reader's identity. Remove only those that feel exaggerated or unsuitable.</p>
                        <div className="flex flex-wrap gap-1.5 min-h-8">
                          {readerDraft.liked_tropes.map((taste) => <button key={`like-${taste}`} type="button" onClick={() => removeDraftTaste("liked_tropes", taste)} title="Remove this taste" className="flex items-center gap-1 text-xs text-sage bg-sage/10 px-2 py-1">+ {taste}<X className="w-3 h-3" /></button>)}
                          {readerDraft.disliked_tropes.map((taste) => <button key={`dislike-${taste}`} type="button" onClick={() => removeDraftTaste("disliked_tropes", taste)} title="Remove this taste" className="flex items-center gap-1 text-xs text-clay bg-clay/10 px-2 py-1">− {taste}<X className="w-3 h-3" /></button>)}
                          {readerDraft.liked_tropes.length === 0 && readerDraft.disliked_tropes.length === 0 && <span className="text-xs text-ink-400">No generated tastes retained.</span>}
                        </div>

                        <label className="text-xs uppercase tracking-widest text-ink-400 block mt-6 mb-2">Optional note to this reader</label>
                        <textarea
                          value={readerDraft.writer_focus_note}
                          onChange={(event) => setReaderDraft((current) => ({ ...current, writer_focus_note: event.target.value.slice(0, 160) }))}
                          placeholder="e.g. Watch whether the romance feels earned."
                          className="w-full h-24 border border-ink-900/12 bg-paper p-3 text-sm text-ink-700 focus:outline-none focus:border-clay resize-none"
                        />
                        <p className="text-right text-[10px] text-ink-400 mt-1">{readerDraft.writer_focus_note.length}/160</p>
                      </div>
                    </div>

                    <div className="mt-6 pt-4 border-t border-ink-900/6 flex items-center justify-between gap-4">
                      <p className="text-xs text-ink-400">This configuration locks permanently when reading begins.</p>
                      <button onClick={saveReaderCustomization} disabled={savingReaderFocus} className="flex items-center gap-2 bg-clay text-white px-5 py-2.5 text-sm disabled:opacity-40" data-testid="save-reader-focus">
                        {savingReaderFocus ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save focus
                      </button>
                    </div>
                  </motion.div>
                );
              })()}

              {repeatedPrimaryFocuses.length > 0 && (
                <div className="mb-5 border border-gold/30 bg-gold/5 px-4 py-3 text-xs text-ink-600">
                  Several readers share the same primary focus: {repeatedPrimaryFocuses.join(", ")}. That is allowed, but a more varied panel usually produces less repetitive feedback.
                </div>
              )}

              {costEstimate && (
                <div className="mb-5 border border-ink-900/10 bg-white px-4 py-3 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-500">
                  <span>Selected readers + first editor report: about {Number(costEstimate.estimated_credits || 0).toFixed(2)} credits</span>
                  <span className={costEstimate.can_start ? "text-sage" : "text-red-600"}>{costEstimate.can_start ? "Credits available" : "Add credits on the billing page to start"}</span>
                </div>
              )}

              <div className="mb-8">
                <button
                  data-testid="add-reader-btn"
                  onClick={addReader}
                  disabled={loading || selectedReaderIds.length >= MAX_READERS}
                  title={selectedReaderIds.length >= MAX_READERS ? "Maximum 5 readers." : "Add another reader"}
                  className="flex items-center gap-2 border border-ink-900/12 hover:border-clay text-ink-600 hover:text-clay px-5 py-2.5 text-sm font-medium transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-ink-900/12 disabled:hover:text-ink-600"
                  style={{ borderRadius: "2px" }}
                >
                  <Plus className="w-4 h-4" strokeWidth={1.5} />
                  Add Reader
                </button>
                {selectedReaderIds.length >= MAX_READERS && (
                  <p className="text-xs text-ink-400 mt-1.5">Maximum 5 readers.</p>
                )}
              </div>

              <div className="flex justify-between">
                <button
                  data-testid="back-to-genre-btn"
                  onClick={() => setStep("genre")}
                  className="text-sm text-ink-600 hover:text-ink-900 transition-colors"
                >
                  ← Back
                </button>
                <button
                  data-testid="start-reading-btn"
                  onClick={startReading}
                  disabled={personas.length === 0 || selectedReaderIds.length === 0 || !costEstimate?.can_start}
                  className="flex items-center gap-2 bg-clay hover:bg-clay-hover text-white px-8 py-3 text-sm font-semibold transition-all duration-200 disabled:opacity-40"
                  style={{ borderRadius: "2px" }}
                >
                  <BookOpen className="w-4 h-4" strokeWidth={1.5} />
                  Start Reading
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
