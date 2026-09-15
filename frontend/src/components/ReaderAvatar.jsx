import React, { useState } from "react";
import { readerPalette, readerPaletteIndex } from "../readerPalette";

export default function ReaderAvatar({ name = "Reader", index = 0 }) {
  const avatarIndex = readerPaletteIndex(index);
  const src = `${process.env.PUBLIC_URL}/readers/reader-${avatarIndex}.jpg`;
  const [failedSrc, setFailedSrc] = useState(null);
  const { tint: background, color } = readerPalette(avatarIndex);
  return <span className="reader-avatar" aria-hidden="true" style={{ background, color, border: `1px solid ${color}` }}>
    {failedSrc === src ? String(name || "Reader").trim().charAt(0).toUpperCase() || "R" :
      <img src={src} alt="" onError={() => setFailedSrc(src)} />}
  </span>;
}
