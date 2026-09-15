// Stable reader identity colors, shared by profiles, portraits, and annotations.
const READER_PALETTE = [
  { color: "#8A4545", tint: "#F3E7E3" }, // Oxblood
  { color: "#405F79", tint: "#E8EDF1" }, // Ink blue
  { color: "#947126", ink: "#806020", tint: "#F3EDD9" }, // Antique gold
  { color: "#79604B", tint: "#EFE8E0" }, // Walnut
  { color: "#596B73", tint: "#E8ECEC" }, // Slate
];

export function readerPaletteIndex(index = 0) {
  const number = Number(index);
  return Number.isFinite(number) ? Math.abs(Math.trunc(number)) % READER_PALETTE.length : 0;
}

export function readerPalette(index = 0) {
  return READER_PALETTE[readerPaletteIndex(index)];
}

export function readerColorStyle(index = 0) {
  const { color, ink = color, tint } = readerPalette(index);
  return { "--reader-color": color, "--reader-ink": ink, "--reader-tint": tint };
}
