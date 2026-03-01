import re
from typing import List, Dict, Tuple

TARGET_WORDS_PER_SECTION = 1200  # target chunk size when sub-splitting large chapters
BATCH_THRESHOLD = 800            # chapters under this get batched together
SPLIT_THRESHOLD = 2500           # chapters over this get sub-split

_scene_break_pattern = re.compile(
    r'\n[ \t]*(?:\*{2,}|\-{2,}|#{2,}|~{2,}|_{2,}|\.{3,})[ \t]*\n|\n{3,}',
    re.MULTILINE,
)


def split_manuscript(raw_text: str) -> Tuple[List[Dict], int]:
    """
    Split manuscript into reading sections:
    1. Detect chapter headings
    2. Batch consecutive short chapters (<2000 words) together
    3. Sub-split only chapters exceeding 5000 words at paragraph boundaries (~500w chunks)
    4. Detect scene breaks within chapters before sub-splitting
    5. Assign continuous global line numbers (paragraph = 1 line)
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

    # Batch consecutive short chapters together
    batched: List[Dict] = []
    i = 0
    while i < len(raw_chapters):
        ch = raw_chapters[i]
        wc = len(ch["text"].split())
        if wc < BATCH_THRESHOLD and i + 1 < len(raw_chapters):
            combined_text = ch["text"]
            combined_title = ch["title"]
            j = i + 1
            while j < len(raw_chapters):
                next_wc = len(raw_chapters[j]["text"].split())
                if len(combined_text.split()) + next_wc <= SPLIT_THRESHOLD:
                    combined_text += "\n\n" + raw_chapters[j]["text"]
                    combined_title = f"{combined_title} & {raw_chapters[j]['title']}"
                    j += 1
                    if next_wc >= BATCH_THRESHOLD:
                        break
                else:
                    break
            batched.append({"title": combined_title, "text": combined_text})
            i = j
        else:
            batched.append(ch)
            i += 1

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

    sections: List[Dict] = []
    global_line = 1
    for idx, seg in enumerate(final_segments):
        paragraphs = [p.strip() for p in seg["text"].split("\n") if p.strip()]
        line_start = global_line
        paragraph_lines = [{"line": global_line + k, "text": p} for k, p in enumerate(paragraphs)]
        global_line += len(paragraphs)
        line_end = global_line - 1
        sections.append({
            "section_number": idx + 1,
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
