import React, { useState, useEffect } from "react";
import { Settings2, ChevronDown, Check } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

export const ModelSelector = () => {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState({ provider: "openai", model: "gpt-4o", label: "GPT-4o" });
  const [models, setModels] = useState([]);

  useEffect(() => {
    loadModels();
  }, []);

  const loadModels = async () => {
    try {
      const res = await axios.get(`${API}/config/models`);
      setModels(res.data.available || []);
      const found = res.data.available?.find(
        (m) => m.model === res.data.current_model && m.provider === res.data.current_provider
      );
      if (found) setCurrent(found);
    } catch {}
  };

  const selectModel = async (m) => {
    try {
      await axios.post(`${API}/config/model`, { provider: m.provider, model: m.model });
      setCurrent(m);
      setOpen(false);
      toast.success(`Switched to ${m.label}`);
    } catch {
      toast.error("Failed to update model");
    }
  };

  // Group by provider
  const grouped = models.reduce((acc, m) => {
    if (!acc[m.provider]) acc[m.provider] = [];
    if (!acc[m.provider].find((x) => x.model === m.model)) acc[m.provider].push(m);
    return acc;
  }, {});

  return (
    <div className="relative">
      <button
        data-testid="model-selector-btn"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 text-xs text-ink-600 border border-ink-900/12 hover:border-clay hover:text-clay px-3 py-2 transition-all"
        style={{ borderRadius: "2px", fontFamily: "'Manrope', sans-serif" }}
      >
        <Settings2 className="w-3.5 h-3.5" strokeWidth={1.5} />
        <span>{current.label}</span>
        <ChevronDown className="w-3 h-3" strokeWidth={1.5} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div
            className="absolute right-0 top-full mt-2 bg-white border border-ink-900/10 shadow-lg z-40 min-w-48 py-2"
            style={{ borderRadius: "2px" }}
          >
            <p className="text-xs text-ink-400 uppercase tracking-widest px-3 pb-2">AI Model</p>
            {Object.entries(grouped).map(([provider, ms]) => (
              <div key={provider}>
                <p className="text-xs text-ink-400 px-3 py-1.5 border-t border-ink-900/6 mt-1 capitalize">
                  {provider}
                </p>
                {ms.map((m) => (
                  <button
                    key={m.model}
                    data-testid={`model-option-${m.model}`}
                    onClick={() => selectModel(m)}
                    className="w-full flex items-center justify-between px-3 py-2 text-sm text-ink-900 hover:bg-paper-dark transition-colors text-left"
                  >
                    {m.label}
                    {current.model === m.model && (
                      <Check className="w-3.5 h-3.5 text-clay" strokeWidth={1.5} />
                    )}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

export default ModelSelector;
