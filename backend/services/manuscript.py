import re
from typing import List, Dict, Tuple

TARGET_WORDS_PER_SECTION = 6000
MAX_WORDS_PER_SECTION = 8000
MIN_WORDS_PER_SECTION = 3000
SPLIT_THRESHOLD = 8000

_scene_break_pattern = re.compile(
    r'\n[ \t]*(?:\*{2,}|\-{2,}|#{2,}|~{2,}|_{2,}|\.{3,})[ \t]*\n|\n{3,}',
    re.MULTILINE,
)


def split_manuscript(raw_text: str) -> Tuple[List[Dict], int]:
    """
    Split manuscript into reading sections.
    Prefer breaks at: chapter boundaries, scene breaks (blank lines or ***/---), paragraph boundaries.
    Target 6000 words per section, max 8000, min 3000. If last section would be < 3000 words, merge into previous.
    """
    chapter_pattern = re.compile(
        r'(?:^|\n)[ \t]*((?:chapter|prologue|epilogue|part|act|scene|section|interlude|coda|preface|introduction|afterword|appendix)'
        r'[\s\.\-:]*[\w\d\s\.\-:\'\"]*?)'
        r'(?:\n|$)',
        re.IGNORECASE,
    )
    chapter_matches = list(chapter_pattern.finditer(raw_text))

    raw_chapters: List[Dict] = []
    if len(chapter_matches) >= 2:
        for i, match in enumerate(chapter_matches):
            start = match.start()
            end = chapter_matches[i + 1].start() if i + 1 < len(chapter_matches) else len(raw_text)
            title = match.group(1).strip()
            text = raw_text[start:end].strip()
            if len(text.split()) > 30:
                raw_chapters.append({"title": title, "text": text})

    if not raw_chapters:
        raw_chapters = [{"title": "Manuscript", "text": raw_text.strip()}]

    batched: List[Dict] = []
    current_parts: List[Dict] = []
    current_words = 0

    for ch in raw_chapters:
        wc = len(ch["text"].split())
        if wc >= MAX_WORDS_PER_SECTION:
            if current_parts:
                batched.append({
                    "title": " & ".join(p["title"] for p in current_parts),
                    "text": "\n\n".join(p["text"] for p in current_parts),
                })
                current_parts, current_words = [], 0
            batched.append(ch)
        elif current_words + wc > TARGET_WORDS_PER_SECTION and current_parts:
            batched.append({
                "title": " & ".join(p["title"] for p in current_parts),
                "text": "\n\n".join(p["text"] for p in current_parts),
            })
            current_parts, current_words = [ch], wc
        else:
            current_parts.append(ch)
            current_words += wc

    if current_parts:
        batched.append({
            "title": " & ".join(p["title"] for p in current_parts),
            "text": "\n\n".join(p["text"] for p in current_parts),
        })

    def _split_on_scenes(title: str, text: str) -> List[Dict]:
        parts = _scene_break_pattern.split(text)
        result = []
        for k, part in enumerate(parts):
            part = part.strip()
            if not part or len(part.split()) < 20:
                continue
            t = title if k == 0 else f"{title} (scene {k + 1})"
            result.append({"title": t, "text": part})
        return result or [{"title": title, "text": text}]

    def _sub_split(title: str, text: str) -> List[Dict]:
        words = text.split()
        if len(words) <= SPLIT_THRESHOLD:
            return [{"title": title, "text": text}]
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        chunks, current_paras, current_words, part_num = [], [], 0, 0
        for para in paragraphs:
            pw = len(para.split())
            if current_words + pw > TARGET_WORDS_PER_SECTION and current_paras:
                part_num += 1
                label = title if part_num == 1 else f"{title}, part {part_num}"
                chunks.append({"title": label, "text": "\n\n".join(current_paras)})
                current_paras, current_words = [para], pw
            else:
                current_paras.append(para)
                current_words += pw
        if current_paras:
            part_num += 1
            label = title if part_num == 1 else f"{title}, part {part_num}"
            chunks.append({"title": label, "text": "\n\n".join(current_paras)})
        return chunks

    final_segments: List[Dict] = []
    for ch in batched:
        scenes = _split_on_scenes(ch["title"], ch["text"])
        for sc in scenes:
            final_segments.extend(_sub_split(sc["title"], sc["text"]))

    if not final_segments:
        return [], 0

    while len(final_segments) > 1 and len(final_segments[-1]["text"].split()) < MIN_WORDS_PER_SECTION:
        last = final_segments.pop()
        prev = final_segments[-1]
        combined = prev["text"] + "\n\n" + last["text"]
        final_segments[-1] = {"title": prev["title"], "text": combined}

    sections: List[Dict] = []
    global_line = 1
    section_number = 0
    for seg in final_segments:
        paragraphs = [p.strip() for p in seg["text"].split("\n") if p.strip()]
        if not paragraphs:
            continue
        section_number += 1
        line_start = global_line
        paragraph_lines = [{"line": global_line + k, "text": p} for k, p in enumerate(paragraphs)]
        global_line += len(paragraph_lines)
        line_end = global_line - 1
        sections.append({
            "section_number": section_number,
            "title": seg["title"],
            "text": seg["text"],
            "start_char": 0,
            "end_char": 0,
            "line_start": line_start,
            "line_end": line_end,
            "paragraph_lines": paragraph_lines,
            "word_count": len(seg["text"].split()),
        })

    return sections, global_line - 1
