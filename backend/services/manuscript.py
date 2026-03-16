import re
import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

# Section limits: keep sections in 500-2500 range so Gemini reliably completes full output
MAX_SECTION_WORDS = 2500
MIN_SECTION_WORDS = 500

# Legacy constants for any callers that expect the old targets
TARGET_WORDS_PER_SECTION = 2000
TARGET_WORDS = 2000
SPLIT_THRESHOLD = MAX_SECTION_WORDS

# Chapter markers: "Chapter X", "CHAPTER", "---", "***", or 3+ blank lines
_chapter_heading_re = re.compile(
    r"^(?:chapter|prologue|epilogue|part|act|scene|section|interlude|coda|preface|introduction|afterword|appendix)"
    r"[\s.\-:]*[\w\d\s.\-:'\"]*$",
    re.IGNORECASE,
)
_scene_marker_re = re.compile(r"^[\*\-]{2,}$")


def _parse_paragraphs_with_breaks(raw_text: str) -> List[Tuple[str, str]]:
    """
    Split text into paragraphs and classify the break type after each paragraph.
    Returns list of (paragraph_text, break_after) where break_after is "chapter" | "scene" | "paragraph".
    Uses line-level granularity: each non-empty line is one entry, so we have enough break points to
    hit 3000-word targets even when the manuscript has few blank lines (e.g. 5 long chapters).
    """
    lines = raw_text.split("\n")
    blocks: List[Tuple[str, str]] = []
    current: List[str] = []
    blank_lines_before = 0

    for line in lines:
        if line.strip():
            if blank_lines_before > 0 and current:
                prev_text = "\n".join(current).strip()
                if prev_text:
                    break_after = "chapter" if blank_lines_before >= 3 else "scene"
                    blocks.append((prev_text, break_after))
                current = []
            current.append(line.strip())
            blank_lines_before = 0
        else:
            blank_lines_before += 1

    if current:
        prev_text = "\n".join(current).strip()
        if prev_text:
            blocks.append((prev_text, "paragraph"))

    # Override: if a block starts with a chapter heading, the break before it is chapter
    result_blocks: List[Tuple[str, str]] = []
    for i, (para_text, break_after) in enumerate(blocks):
        if i > 0 and (_chapter_heading_re.match(para_text.split("\n")[0].strip()) or _scene_marker_re.match(para_text.strip())):
            result_blocks[-1] = (result_blocks[-1][0], "chapter")
        result_blocks.append((para_text, break_after))

    # Expand to line-level so we have a break point every line (enables 3000-word splits when blocks are huge)
    paragraphs: List[Tuple[str, str]] = []
    for block_text, break_after in result_blocks:
        block_lines = [ln.strip() for ln in block_text.split("\n") if ln.strip()]
        for line in block_lines:
            paragraphs.append((line, "paragraph"))
        if paragraphs:
            paragraphs[-1] = (paragraphs[-1][0], break_after)
    return paragraphs


def _chapter_ranges(parsed: List[Tuple[str, str]]) -> List[Tuple[int, int]]:
    """Return list of (start_idx, end_idx) for each chapter. Chapters are split on chapter/scene breaks."""
    if not parsed:
        return []
    starts = [0]
    for i in range(len(parsed)):
        if parsed[i][1] == "chapter":
            starts.append(i + 1)
    ranges: List[Tuple[int, int]] = []
    for j in range(len(starts)):
        s = starts[j]
        e = starts[j + 1] if j + 1 < len(starts) else len(parsed)
        if s < e:
            ranges.append((s, e))
    return ranges


def _segment_words(cum_words: List[int], start_idx: int, end_idx: int) -> int:
    """Word count for segment [start_idx, end_idx] (inclusive)."""
    if start_idx > end_idx:
        return 0
    before = cum_words[start_idx - 1] if start_idx > 0 else 0
    return cum_words[end_idx] - before


def _subsplit_range(
    parsed: List[Tuple[str, str]],
    cum_words: List[int],
    start_idx: int,
    end_idx: int,
) -> List[Tuple[int, int]]:
    """
    If segment [start_idx, end_idx] exceeds MAX_SECTION_WORDS, split at paragraph boundary
    nearest to midpoint. Both parts must be >= MIN_SECTION_WORDS and <= MAX_SECTION_WORDS.
    Never split mid-paragraph (we split at index boundaries). Recursively sub-split until all <= max.
    """
    words = _segment_words(cum_words, start_idx, end_idx)
    if words <= MAX_SECTION_WORDS:
        return [(start_idx, end_idx)]

    start_words = cum_words[start_idx - 1] if start_idx > 0 else 0
    end_words = cum_words[end_idx]
    mid_target = start_words + (end_words - start_words) // 2

    best_k: int | None = None
    best_dist = float("inf")
    for k in range(start_idx, end_idx):
        first_words = cum_words[k] - start_words
        second_words = end_words - cum_words[k]
        if first_words < MIN_SECTION_WORDS or second_words < MIN_SECTION_WORDS:
            continue
        if first_words > MAX_SECTION_WORDS or second_words > MAX_SECTION_WORDS:
            continue
        dist = abs((cum_words[k]) - mid_target)
        if dist < best_dist:
            best_dist = dist
            best_k = k
    if best_k is None:
        # No valid split that keeps both >= 500 and <= 2500; force at midpoint anyway to avoid huge section
        for k in range(start_idx, end_idx):
            first_words = cum_words[k] - start_words
            second_words = end_words - cum_words[k]
            if first_words >= MIN_SECTION_WORDS and second_words >= MIN_SECTION_WORDS:
                best_k = k
                break
        if best_k is None:
            return [(start_idx, end_idx)]

    left = _subsplit_range(parsed, cum_words, start_idx, best_k)
    right = _subsplit_range(parsed, cum_words, best_k + 1, end_idx)
    return left + right


def _merge_small_sections(
    cum_words: List[int],
    ranges: List[Tuple[int, int]],
) -> List[Tuple[int, int]]:
    """Merge any section under MIN_SECTION_WORDS with the next (or previous) section. Repeat until stable."""
    if len(ranges) <= 1:
        return ranges
    while True:
        merged: List[Tuple[int, int]] = []
        i = 0
        changed = False
        while i < len(ranges):
            s, e = ranges[i]
            w = _segment_words(cum_words, s, e)
            if w < MIN_SECTION_WORDS and merged:
                prev_s, prev_e = merged[-1]
                merged[-1] = (prev_s, e)
                changed = True
            elif w < MIN_SECTION_WORDS and i + 1 < len(ranges):
                next_s, next_e = ranges[i + 1]
                merged.append((s, next_e))
                i += 1
                changed = True
            else:
                merged.append((s, e))
            i += 1
        ranges = merged
        if not changed or len(ranges) <= 1:
            break
    return ranges


def split_manuscript_into_sections(raw_text: str) -> List[Dict]:
    """
    Split manuscript into sections: first by chapter breaks, then sub-split any chapter
    over 2500 words at paragraph boundaries near the midpoint. Never split mid-paragraph.
    Minimum section 500 words (merge small fragments into adjacent section).
    Returns list of dicts: text, start_paragraph (1-based), end_paragraph (1-based), word_count.
    """
    parsed = _parse_paragraphs_with_breaks(raw_text.strip())
    if not parsed:
        return []

    words_per_para = [len(p[0].split()) for p in parsed]
    cum_words: List[int] = []
    acc = 0
    for w in words_per_para:
        acc += w
        cum_words.append(acc)

    chapter_ranges = _chapter_ranges(parsed)
    section_ranges: List[Tuple[int, int]] = []
    for s, e in chapter_ranges:
        segment_w = _segment_words(cum_words, s, e)
        if segment_w <= MAX_SECTION_WORDS:
            section_ranges.append((s, e))
        else:
            section_ranges.extend(_subsplit_range(parsed, cum_words, s, e))

    section_ranges = _merge_small_sections(cum_words, section_ranges)

    sections: List[Dict] = []
    for start_idx, end_idx in section_ranges:
        section_text = "\n\n".join(parsed[j][0] for j in range(start_idx, end_idx + 1))
        sec_word_count = len(section_text.split())
        sections.append({
            "text": section_text,
            "start_paragraph": start_idx + 1,
            "end_paragraph": end_idx + 1,
            "word_count": sec_word_count,
        })
        logger.info(
            "Section %s: %s words (paragraphs %s-%s)",
            len(sections), sec_word_count, start_idx + 1, end_idx + 1,
        )
    return sections


def split_manuscript(raw_text: str) -> Tuple[List[Dict], int]:
    """
    Split manuscript into reading sections using smart boundaries (6k target, natural breaks).
    Returns (sections, total_lines) where each section has section_number, title, text,
    line_start, line_end, paragraph_lines, word_count. Global paragraph numbering is preserved.
    paragraph_lines: one entry per non-empty LINE (split by newline), so display and annotations match line numbers.
    """
    raw_text = raw_text.strip()
    if not raw_text:
        return [], 0

    section_dicts = split_manuscript_into_sections(raw_text)
    sections: List[Dict] = []
    parsed = _parse_paragraphs_with_breaks(raw_text)
    global_line = 1
    for sn, sec in enumerate(section_dicts, 1):
        start_para = sec["start_paragraph"]
        end_para = sec["end_paragraph"]
        word_count = sec["word_count"]
        start_idx = start_para - 1
        end_idx = end_para - 1
        paragraph_lines: List[Dict] = []
        for j in range(start_idx, min(end_idx + 1, len(parsed))):
            para_text = parsed[j][0]
            for line in para_text.split("\n"):
                stripped = line.strip()
                if stripped:
                    paragraph_lines.append({"line": global_line, "text": stripped})
                    global_line += 1
        if not paragraph_lines:
            continue
        line_start = paragraph_lines[0]["line"]
        line_end = paragraph_lines[-1]["line"]
        text = "\n\n".join(pl["text"] for pl in paragraph_lines)
        sections.append({
            "section_number": sn,
            "title": f"Section {sn}",
            "text": text,
            "start_char": 0,
            "end_char": 0,
            "line_start": line_start,
            "line_end": line_end,
            "paragraph_lines": paragraph_lines,
            "word_count": word_count,
        })
    total_lines = global_line - 1
    return sections, total_lines
