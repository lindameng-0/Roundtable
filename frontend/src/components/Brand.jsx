import React from "react";
import { Link } from "react-router-dom";

export function TableMark({ className = "" }) {
  return <svg className={className} viewBox="0 0 100 100" fill="none" aria-hidden="true">
    <circle cx="50" cy="50" r="16" stroke="currentColor" strokeWidth="1.5" />
    {[0, 72, 144, 216, 288].map(angle => <g key={angle} transform={`rotate(${angle} 50 50)`}>
      <path d="M50 28V9C43 5 35 6 32 8v18c6-2 12-2 18 2Zm0 0V9c7-4 15-3 18-1v18c-6-2-12-2-18 2Z" stroke="currentColor" strokeWidth="1.5" fill="currentColor" fillOpacity=".06" />
    </g>)}
    <circle cx="50" cy="50" r="3" fill="currentColor" />
  </svg>;
}

export default function Brand({ to = "/", compact = false }) {
  return <Link to={to} className={`brand ${compact ? "brand-compact" : ""}`} aria-label="Roundtable home">
    <TableMark /><span>Roundtable</span>
  </Link>;
}
