import React, { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, LayoutDashboard, LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";

/**
 * Top-right user avatar + dropdown (Dashboard, Sign Out).
 */
export function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (!user) return null;

  return (
    <div className="relative" ref={ref} data-testid="user-menu-container">
      <button
        data-testid="user-menu-trigger"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 hover:opacity-80 transition-opacity"
      >
        {user.picture ? (
          <img src={user.picture} alt={user.name} className="w-7 h-7 rounded-full object-cover border border-ink-900/10" />
        ) : (
          <div className="w-7 h-7 rounded-full bg-clay flex items-center justify-center text-white text-xs font-bold">
            {user.name?.[0] || "U"}
          </div>
        )}
        <span className="hidden sm:block text-sm text-ink-700 max-w-[120px] truncate">{user.name}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-ink-400 transition-transform ${open ? "rotate-180" : ""}`} strokeWidth={1.5} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.96 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 mt-2 w-44 bg-white border border-ink-900/10 shadow-lg z-50"
            style={{ borderRadius: "2px" }}
            data-testid="user-menu-dropdown"
          >
            <div className="p-2.5 border-b border-ink-900/6">
              <p className="text-xs font-medium text-ink-900 truncate">{user.name}</p>
              <p className="text-xs text-ink-400 truncate">{user.email}</p>
            </div>
            <div className="py-1">
              <button
                data-testid="user-menu-dashboard"
                onClick={() => { setOpen(false); navigate("/dashboard"); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-ink-700 hover:bg-paper transition-colors"
              >
                <LayoutDashboard className="w-3.5 h-3.5" strokeWidth={1.5} />
                Dashboard
              </button>
              <button
                data-testid="user-menu-signout"
                onClick={async () => {
                  setOpen(false);
                  await logout();
                  navigate("/login", { replace: true });
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-ink-700 hover:bg-paper transition-colors"
              >
                <LogOut className="w-3.5 h-3.5" strokeWidth={1.5} />
                Sign out
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
