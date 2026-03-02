import re
from typing import List, Dict, Tuple

# Smart section splitting: 2500-4000 word sections for focused reading (was 6k target, 8k max)
TARGET_WORDS = 3000
WINDOW_LOW = 2500
WINDOW_HIGH = 4000
MAX_SECTION_WORDS = 4500
MIN_SECTION_WORDS = 1500

# Legacy constants for any callers that expect the old targets
TARGET_WORDS_PER_SECTION = TARGET_WORDS
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
    """
    lines = raw_text.split("\n")
    paragraphs: List[Tuple[str, str]] = []
    current: List[str] = []
    blank_lines_before = 0

    for line in lines:
        if line.strip():
            if blank_lines_before > 0 and current:
                prev_text = "\n".join(current).strip()
                if prev_text:
                    break_after = "chapter" if blank_lines_before >= 3 else "scene"
                    paragraphs.append((prev_text, break_after))
                current = []
            current.append(line.strip())
            blank_lines_before = 0
        else:
            blank_lines_before += 1
            # Keep current; we'll flush when we see next non-empty (then we know break type)

    if current:
        prev_text = "\n".join(current).strip()
        if prev_text:
            paragraphs.append((prev_text, "paragraph"))

    # Override: if a paragraph is a chapter heading, the break before it is chapter
    result: List[Tuple[str, str]] = []
    for i, (para_text, break_after) in enumerate(paragraphs):
        if i > 0 and (_chapter_heading_re.match(para_text.split("\n")[0].strip()) or _scene_marker_re.match(para_text.strip())):
            result[-1] = (result[-1][0], "chapter")
        result.append((para_text, break_after))

    return result


def split_manuscript_into_sections(raw_text: str) -> List[Dict]:
    """
    Split manuscript into sections with smart boundaries.
    Target 3000 words; look for break in 2500-4000 (chapter > scene > paragraph).
    Never split mid-paragraph; max 4500; min 1500 except last section.
    Returns list of dicts: text, start_paragraph (1-based), end_paragraph (1-based), word_count.
    """
    parsed = _parse_paragraphs_with_breaks(raw_text.strip())
    if not parsed:
        return []

    # Cumulative word count after each paragraph (0-based index -> words up to and including that para)
    words_per_para = [len(p[0].split()) for p in parsed]
    cum_words: List[int] = []
    acc = 0
    for w in words_per_para:
        acc += w
        cum_words.append(acc)
    total_words = cum_words[-1]

    sections: List[Dict] = []
    start_idx = 0
    para_count = len(parsed)

    while start_idx < para_count:
        # Remaining words from start_idx to end
        remaining = total_words - (cum_words[start_idx - 1] if start_idx > 0 else 0)
        if remaining <= 0:
            break

        # If remainder is under MIN and we already have sections, take the rest as final section
        if sections and remaining < MIN_SECTION_WORDS:
            end_idx = para_count - 1
            section_text = "\n\n".join(parsed[i][0] for i in range(start_idx, end_idx + 1))
            sections.append({
                "text": section_text,
                "start_paragraph": start_idx + 1,
                "end_paragraph": end_idx + 1,
                "word_count": len(section_text.split()),
            })
            break

        # Target: find best break in [WINDOW_LOW, WINDOW_HIGH] or force by MAX_SECTION_WORDS
        start_words = cum_words[start_idx - 1] if start_idx > 0 else 0
        target_end_words = min(start_words + TARGET_WORDS, start_words + MAX_SECTION_WORDS)
        search_low = start_words + WINDOW_LOW
        search_high = min(start_words + WINDOW_HIGH, start_words + MAX_SECTION_WORDS)

        best_idx: int | None = None
        best_priority = -1  # chapter=2, scene=1, paragraph=0

        # Prefer chapter break in 2500-4500 range
        for i in range(start_idx, para_count):
            w_after = cum_words[i]
            if w_after > start_words + MAX_SECTION_WORDS:
                break
            if w_after < start_words + MIN_SECTION_WORDS and i < para_count - 1:
                continue
            break_after = parsed[i][1]
            if break_after == "chapter":
                best_idx = i
                best_priority = 2
                if WINDOW_LOW <= (w_after - start_words) <= WINDOW_HIGH:
                    break
        if best_idx is not None:
            end_idx = best_idx
            section_text = "\n\n".join(parsed[j][0] for j in range(start_idx, end_idx + 1))
            sections.append({
                "text": section_text,
                "start_paragraph": start_idx + 1,
                "end_paragraph": end_idx + 1,
                "word_count": len(section_text.split()),
            })
            start_idx = end_idx + 1
            continue

        # Look for scene or paragraph break in 2500-4000, then up to 4500
        for i in range(start_idx, para_count):
            w_after = cum_words[i]
            if w_after > start_words + MAX_SECTION_WORDS:
                break
            segment_words = w_after - start_words
            if segment_words < MIN_SECTION_WORDS and i < para_count - 1:
                continue
            break_after = parsed[i][1]
            prio = 1 if break_after == "scene" else 0
            if prio >= best_priority:
                if best_priority == prio and best_idx is not None:
                    # Prefer break closer to 3000
                    best_seg = cum_words[best_idx] - start_words if best_idx is not None else 0
                    if abs(segment_words - TARGET_WORDS) < abs(best_seg - TARGET_WORDS):
                        best_idx = i
                else:
                    best_idx = i
                    best_priority = prio
            if segment_words >= WINDOW_HIGH and best_idx is not None:
                break

        if best_idx is not None:
            end_idx = best_idx
        else:
            # Force split at paragraph before exceeding 4500
            end_idx = start_idx
            for i in range(start_idx, para_count):
                if cum_words[i] - start_words > MAX_SECTION_WORDS:
                    break
                end_idx = i
            if end_idx < start_idx:
                end_idx = start_idx

        section_text = "\n\n".join(parsed[j][0] for j in range(start_idx, end_idx + 1))
        sections.append({
            "text": section_text,
            "start_paragraph": start_idx + 1,
            "end_paragraph": end_idx + 1,
            "word_count": len(section_text.split()),
        })
        start_idx = end_idx + 1

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
