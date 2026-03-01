import React, { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { UserMenu } from "../components/UserMenu";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { Upload, FileText, ChevronRight, RefreshCw, X, Plus, BookOpen } from "lucide-react";
import axios from "axios";
import ModelSelector from "../components/ModelSelector";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

// Chunked upload: if request body would exceed this (bytes), send in chunks to avoid 413
const SAFE_BODY_SIZE = 100 * 1024 * 1024; // 100MB — full-length books (500+ pages)
const CHUNK_CHARS = 400 * 1024; // 400K chars per chunk

const STEPS = ["manuscript", "genre", "readers"];

const READER_AVATAR_URLS = [
  "https://images.unsplash.com/photo-1581883556531-e5f8027f557f?crop=entropy&cs=srgb&fm=jpg&q=85&w=120",
  "https://images.unsplash.com/photo-1658909835269-e76abd3ffb5d?crop=entropy&cs=srgb&fm=jpg&q=85&w=120",
  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&q=80&w=120",
  "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&q=80&w=120",
  "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&q=80&w=120",
];

const PERSONALITY_COLORS = {
  analytical: "#5C5855",
  emotional: "#C86B56",
  casual: "#8da399",
  skeptical: "#D4Af37",
  genre_savvy: "#2D2A26",
};

export default function SetupPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState("manuscript");
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [manuscript, setManuscript] = useState(null);
  const [genre, setGenre] = useState({});
  const [comparableInput, setComparableInput] = useState("");
  const [personas, setPersonas] = useState([]);
  const [regeneratingId, setRegeneratingId] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  const [uploadedFileName, setUploadedFileName] = useState(null);

  const handleFileUpload = async (file) => {
    if (!file) return;
    const name = file.name || "";
    if (!name.endsWith(".txt") && !name.endsWith(".docx")) {
      toast.error("Please upload a .txt or .docx file");
      return;
    }
    if (name.endsWith(".docx")) {
      // For .docx, upload to backend for extraction
      setLoading(true);
      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("title", title || name.replace(/\.docx$/, ""));
        const headers = {};
        const token = localStorage.getItem("session_token");
        if (token) headers["Authorization"] = `Bearer ${token}`;
        const res = await axios.post(`${API}/manuscripts/upload`, formData, { headers, withCredentials: true });
        // docx upload goes straight to the manuscript — skip text paste step
        setManuscript(res.data);
        setGenre({
          genre: res.data.genre,
          target_audience: res.data.target_audience,
          age_range: res.data.age_range,
          comparable_books: res.data.comparable_books || [],
        });
        setUploadedFileName(name);
        setTitle((t) => t || name.replace(/\.docx$/, ""));
        setStep("genre");
        toast.success(`Extracted text from ${name}`);
      } catch (err) {
        toast.error("Failed to read .docx file");
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
      const token = localStorage.getItem("session_token");
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const payload = { title: title || "Untitled Manuscript", raw_text: text };
      const payloadStr = JSON.stringify(payload);
      // Use byte length (UTF-8), not string length — so we compare bytes to bytes
      const bodySizeBytes = new TextEncoder().encode(payloadStr).length;

      let res;
      if (bodySizeBytes <= SAFE_BODY_SIZE) {
        res = await axios.post(`${API}/manuscripts`, payload, { headers, withCredentials: true });
      } else {
        // Chunked upload to avoid 413 (proxy body limit)
        const firstChunk = text.slice(0, CHUNK_CHARS);
        res = await axios.post(`${API}/manuscripts`, {
          title: title || "Untitled Manuscript",
          raw_text: firstChunk,
        }, { headers, withCredentials: true });
        const manuscriptId = res.data.id;
        for (let start = CHUNK_CHARS; start < text.length; start += CHUNK_CHARS) {
          const chunk = text.slice(start, start + CHUNK_CHARS);
          res = await axios.patch(
            `${API}/manuscripts/${manuscriptId}/append-text`,
            { raw_text_chunk: chunk },
            { headers, withCredentials: true }
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
      setStep("genre");
    } catch (err) {
      const status = err.response?.status;
      const payloadStr = JSON.stringify({ title: title || "Untitled Manuscript", raw_text: text });
      const bodySizeBytes = new TextEncoder().encode(payloadStr).length;
      const sizeMB = (bodySizeBytes / (1024 * 1024)).toFixed(2);
      const msg =
        status === 413
          ? bodySizeBytes <= SAFE_BODY_SIZE
            ? `Server rejected the request (413). Your manuscript is ${sizeMB} MB, under the 100 MB limit — the server may need a higher upload limit.`
            : "Manuscript is too large for the server limit (max 100 MB)."
          : (err.response?.data?.detail ?? err.response?.data?.message ?? err.message ?? "Failed to process manuscript. Please try again.");
      const msgText = Array.isArray(msg) ? msg.map((m) => m.msg ?? m).join(", ") : msg;
      toast.error(msgText);
    } finally {
      setLoading(false);
    }
  };

  const saveGenreAndProceed = async () => {
    setLoading(true);
    try {
      await axios.patch(`${API}/manuscripts/${manuscript.id}/genre`, genre);
      // Generate personas — can take 20-40s for 5 parallel LLM calls
      const res = await axios.get(`${API}/manuscripts/${manuscript.id}/personas`, { timeout: 90000 });
      if (!res.data || res.data.length === 0) {
        throw new Error("No personas returned");
      }
      setPersonas(res.data);
      setStep("readers");
    } catch (err) {
      toast.error("Reader generation timed out or failed. Please try again.");
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
      });
      setPersonas((prev) => prev.map((p) => (p.id === readerId ? res.data : p)));
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
      const res = await axios.post(`${API}/manuscripts/${manuscript.id}/personas/regenerate`, {});
      setPersonas(res.data);
      toast.success("All readers regenerated");
    } catch (err) {
      toast.error("Failed to regenerate readers");
    } finally {
      setLoading(false);
    }
  };

  const startReading = () => {
    navigate(`/read/${manuscript.id}`);
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
    <div className="min-h-screen bg-paper font-sans" style={{ fontFamily: "'Manrope', sans-serif" }}>
      {/* Header */}
      <header className="border-b border-ink-900/8 bg-paper sticky top-0 z-20">
        <div className="max-w-5xl mx-auto px-8 py-5 flex items-center justify-between">
          <div>
            <h1 className="font-serif text-2xl text-ink-900 tracking-tight" style={{ fontFamily: "'Cormorant Garamond', serif" }}>
              Roundtable
            </h1>
            <p className="text-xs text-ink-400 tracking-widest uppercase mt-0.5">A panel of readers for your story</p>
          </div>
          <div className="flex items-center gap-4">
            <ModelSelector />
            <UserMenu />
          </div>
        </div>
      </header>

      {/* Step indicator */}
      <div className="max-w-5xl mx-auto px-8 pt-8">
        <div className="flex items-center gap-3 mb-10">
          {[
            { key: "manuscript", label: "Manuscript" },
            { key: "genre", label: "Genre & Audience" },
            { key: "readers", label: "Meet Your Readers" },
          ].map((s, i) => (
            <React.Fragment key={s.key}>
              <div className="flex items-center gap-2">
                <div
                  className={`w-6 h-6 flex items-center justify-center text-xs font-semibold border transition-all duration-300 ${
                    i < stepIndex
                      ? "bg-clay border-clay text-white"
                      : i === stepIndex
                      ? "border-clay text-clay"
                      : "border-ink-400/30 text-ink-400"
                  }`}
                  style={{ borderRadius: "2px" }}
                >
                  {i < stepIndex ? "✓" : i + 1}
                </div>
                <span className={`text-sm ${i === stepIndex ? "text-ink-900 font-medium" : "text-ink-400"}`}>
                  {s.label}
                </span>
              </div>
              {i < 2 && <div className="flex-1 h-px bg-ink-900/10 max-w-16" />}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-8 pb-20">
        <AnimatePresence mode="wait">
          {/* ── Step 1: Manuscript ── */}
          {step === "manuscript" && (
            <motion.div
              key="manuscript"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.35 }}
            >
              <div className="mb-8">
                <h2 className="font-serif text-4xl text-ink-900 mb-3" style={{ fontFamily: "'Cormorant Garamond', serif" }}>
                  Bring your manuscript to the table
                </h2>
                <p className="text-ink-600 text-base">
                  Paste your text or upload a <strong>.txt</strong> or <strong>.docx</strong> file. Roundtable will assemble a panel of readers just for your story.
                </p>
              </div>

              <div className="mb-4">
                <input
                  data-testid="manuscript-title-input"
                  type="text"
                  placeholder="Manuscript title (optional)"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full border border-ink-900/12 bg-white px-4 py-3 text-sm text-ink-900 placeholder:text-ink-400 focus:outline-none focus:border-clay transition-colors"
                  style={{ borderRadius: "2px" }}
                />
              </div>

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
                <textarea
                  data-testid="manuscript-text-area"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Paste your manuscript here... or drag and drop a .txt or .docx file above"
                  className="w-full h-80 bg-transparent border-none focus:outline-none focus:ring-0 p-6 manuscript-text resize-none placeholder:text-ink-400/50"
                  style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: "1.05rem", lineHeight: "1.85" }}
                />
                {dragOver && (
                  <div className="absolute inset-0 flex items-center justify-center bg-paper/80 pointer-events-none">
                    <div className="text-center">
                      <Upload className="w-8 h-8 text-clay mx-auto mb-2" strokeWidth={1.5} />
                      <p className="text-clay font-medium">Drop your .txt or .docx file</p>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-between">
                <label
                  data-testid="file-upload-label"
                  className="flex items-center gap-2 text-sm text-ink-600 cursor-pointer hover:text-clay transition-colors"
                >
                  <Upload className="w-4 h-4" strokeWidth={1.5} />
                  {uploadedFileName ? (
                    <span className="text-clay font-medium truncate max-w-xs" data-testid="uploaded-filename">{uploadedFileName}</span>
                  ) : (
                    "Upload .txt or .docx"
                  )}
                  <input
                    type="file"
                    accept=".txt,.docx"
                    className="hidden"
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
                <h2 className="font-serif text-4xl text-ink-900 mb-3" style={{ fontFamily: "'Cormorant Garamond', serif" }}>
                  Your story's identity
                </h2>
                <p className="text-ink-600 text-base">
                  We've auto-detected these details. Edit them if needed — your readers will be tailored to match.
                </p>
              </div>

              <div className="bg-white border border-ink-900/8 p-8 space-y-6" style={{ borderRadius: "2px" }}>
                {/* Genre */}
                <div>
                  <label className="text-xs text-ink-400 uppercase tracking-widest block mb-2">Genre</label>
                  <input
                    data-testid="genre-input"
                    value={genre.genre || ""}
                    onChange={(e) => setGenre((g) => ({ ...g, genre: e.target.value }))}
                    className="w-full border border-ink-900/12 px-4 py-2.5 text-sm text-ink-900 focus:outline-none focus:border-clay transition-colors bg-paper"
                    style={{ borderRadius: "2px" }}
                  />
                </div>

                {/* Target Audience */}
                <div>
                  <label className="text-xs text-ink-400 uppercase tracking-widest block mb-2">Target Audience</label>
                  <input
                    data-testid="audience-input"
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
                      data-testid="comparable-book-input"
                      value={comparableInput}
                      onChange={(e) => setComparableInput(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && addComparable()}
                      placeholder="Add a comparable book..."
                      className="flex-1 border border-ink-900/12 px-3 py-2 text-sm focus:outline-none focus:border-clay transition-colors bg-paper"
                      style={{ borderRadius: "2px" }}
                    />
                    <button
                      data-testid="add-comparable-btn"
                      onClick={addComparable}
                      className="px-3 py-2 border border-ink-900/12 hover:border-clay text-ink-600 hover:text-clay transition-colors"
                      style={{ borderRadius: "2px" }}
                    >
                      <Plus className="w-4 h-4" strokeWidth={1.5} />
                    </button>
                  </div>
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
                  <h2 className="font-serif text-4xl text-ink-900 mb-3" style={{ fontFamily: "'Cormorant Garamond', serif" }}>
                    Your reading panel
                  </h2>
                  <p className="text-ink-600 text-base">
                    Five readers, each with their own perspective. Regenerate any you'd like to change.
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

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-8">
                {personas.map((p, i) => (
                  <motion.div
                    key={p.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.08 }}
                    data-testid={`reader-card-${i}`}
                    className="bg-white border border-ink-900/8 p-6 relative group hover:shadow-md transition-all duration-300"
                    style={{ borderRadius: "2px" }}
                  >
                    {/* Regen button */}
                    <button
                      data-testid={`regen-reader-${i}`}
                      onClick={() => regenerateReader(p.id)}
                      disabled={regeneratingId === p.id}
                      className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity text-ink-400 hover:text-clay"
                    >
                      <RefreshCw
                        className={`w-3.5 h-3.5 ${regeneratingId === p.id ? "animate-spin" : ""}`}
                        strokeWidth={1.5}
                      />
                    </button>

                    {/* Avatar + name */}
                    <div className="flex items-start gap-3 mb-4">
                      <div className="w-12 h-12 overflow-hidden flex-shrink-0" style={{ borderRadius: "2px" }}>
                        <img
                          src={READER_AVATAR_URLS[p.avatar_index % READER_AVATAR_URLS.length]}
                          alt={p.name}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            e.target.style.display = "none";
                            e.target.parentElement.style.background = "#F5F2EB";
                          }}
                        />
                      </div>
                      <div>
                        <h3 className="font-medium text-ink-900 text-base">{p.name}</h3>
                        <p className="text-xs text-ink-400">
                          {p.age} · {p.occupation}
                        </p>
                      </div>
                    </div>

                    {/* Personality badge */}
                    <div className="mb-3">
                      <span
                        className="text-xs uppercase tracking-widest font-semibold px-2 py-1"
                        style={{
                          color: PERSONALITY_COLORS[p.personality] || "#5C5855",
                          backgroundColor: `${PERSONALITY_COLORS[p.personality] || "#5C5855"}15`,
                          borderRadius: "2px",
                        }}
                      >
                        {p.personality}
                      </span>
                    </div>

                    {/* Reading habits */}
                    <p className="text-xs text-ink-600 mb-3 leading-relaxed">{p.reading_habits}</p>

                    {/* Quote */}
                    <blockquote
                      className="text-sm text-ink-600 border-l-2 border-clay pl-3 mt-3"
                      style={{ fontFamily: "'Cormorant Garamond', serif", fontStyle: "italic", fontSize: "0.95rem" }}
                    >
                      "{p.quote}"
                    </blockquote>

                    {/* Tropes */}
                    <div className="mt-4 pt-3 border-t border-ink-900/6">
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
                  </motion.div>
                ))}
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
                  disabled={personas.length === 0}
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
      </div>
    </div>
  );
}
