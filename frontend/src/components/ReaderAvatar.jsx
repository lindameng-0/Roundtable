import React from "react";

const palettes = [["#eee3ee", "#66466a"], ["#e7ecdf", "#526653"], ["#eee7d8", "#7c6230"], ["#e4e9ec", "#4b626d"], ["#ebe3dd", "#785d4e"]];
export default function ReaderAvatar({ name = "Reader", index = 0 }) {
  const [background, color] = palettes[Math.abs(index || 0) % palettes.length];
  return <span className="reader-avatar" aria-hidden="true" style={{ background, color }}>{name.trim().charAt(0).toUpperCase() || "R"}</span>;
}
