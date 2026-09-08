import React from "react";
import { X, ChevronLeft, ChevronRight, ArrowUp, MessageSquare } from "lucide-react";
import ReaderAvatar from "./ReaderAvatar";
import { readerColorStyle } from "../readerPalette";

function PassageNotes({ line, comments, personas, close, previous, next, position, count }) {
  return <aside id={`notes-${line}`} className="passage-notes" aria-label={`Notes on paragraph ${line}`} data-testid="comment-popover">
    <header className="passage-notes-heading"><span>At this passage</span><button onClick={close} aria-label="Close passage notes"><X size={15} /></button></header>
    <div className="passage-notes-body">
      {comments.map((entry, index) => {
        const persona = personas.find(reader => reader.id === entry.readerId);
        return <article key={`${entry.readerId}-${index}`} className="passage-note" style={readerColorStyle(persona?.avatar_index)}>
          <div className="passage-note-author"><span className="passage-note-avatar"><ReaderAvatar name={entry.readerName} index={persona?.avatar_index} /></span><span>{entry.readerName || persona?.name || "Reader"}</span><small>{entry.comment?.type || "reaction"}</small></div>
          <p>{entry.comment?.comment}</p>
        </article>;
      })}
    </div>
    <footer className="passage-note-navigation"><span>Passage {position + 1} of {count}</span><div><button onClick={previous} disabled={!previous} aria-label="Previous annotated passage"><ChevronLeft size={17} /></button><button onClick={next} disabled={!next} aria-label="Next annotated passage"><ChevronRight size={17} /></button></div></footer>
  </aside>;
}

export function ManuscriptView({ manuscript, commentsByLine, personas, openPopoverLine, onOpenPopover, readingDone, totalCommentCount, focusMode, onOpenReaders, onNavigate }) {
  const sections = [...(manuscript.sections || [])].sort((a,b) => a.section_number - b.section_number);
  const annotated = sections.flatMap(section => section.paragraph_lines || []).filter(paragraph => commentsByLine[paragraph.line]?.length);
  const annotationPositions = new Map(annotated.map((paragraph, index) => [paragraph.line, index]));
  const jump = paragraph => onNavigate(paragraph.paragraph_id || `p-${String(paragraph.line).padStart(6,"0")}`, paragraph.line);
  const close = line => { onOpenPopover(null); document.getElementById(`note-mark-${line}`)?.focus({ preventScroll:true }); };

  return <div className={`reading-document ${focusMode ? "reading-document-focused" : ""}`} data-testid="manuscript-panel">
    <div className="book-opening" id="manuscript-start" tabIndex={-1}>
      <div className="book-title"><p className="book-genre">{manuscript.genre || "Manuscript"}</p><h1>{manuscript.title}</h1><p className="book-details">{sections.length} {sections.length === 1 ? "section" : "sections"}<span aria-hidden="true"> / </span>{totalCommentCount} passage {totalCommentCount === 1 ? "note" : "notes"}</p></div>
      {!focusMode && <aside className="book-margin-intro">
        <button className="book-reader-roster" onClick={onOpenReaders} aria-label={`Open notebook for ${personas.length} readers`}><span className="book-reader-portraits">{personas.map(persona => <span key={persona.id}><ReaderAvatar name={persona.name} index={persona.avatar_index} /></span>)}</span><span>{personas.length} {personas.length === 1 ? "reader" : "readers"} at the table</span></button>
        <p>{totalCommentCount > 0 ? "The marks in the margin lead to your readers' notes. Open one to read alongside the passage." : readingDone ? "Your readers left no passage notes. Open their notebook for reflections." : "As your readers make notes, they will appear in the margin."}</p>
        {annotated.length > 0 && <button className="book-text-link" onClick={() => jump(annotated[0])}>Start with the first note <ChevronRight size={13} /></button>}
      </aside>}
    </div>
    <article className="book-text" aria-label="Manuscript">
      {sections.map(section => <section key={section.section_number} id={`section-${section.section_number}`} tabIndex={-1} className="book-section">
        <h2>{section.title || `Section ${section.section_number}`}</h2>
        {(section.paragraph_lines || []).map(paragraph => {
          const { line, text, paragraph_id: paragraphId } = paragraph;
          const comments = commentsByLine[line] || [];
          const readerIds = [...new Set(comments.map(comment => comment.readerId))];
          const isOpen = !focusMode && openPopoverLine === line;
          const position = annotationPositions.get(line);
          return <div key={paragraphId || line} id={paragraphId || `p-${String(line).padStart(6,"0")}`} tabIndex={-1} className={`prose-paragraph ${isOpen ? "prose-paragraph-selected" : ""}`}>
            <p className="book-prose" data-line={line} data-paragraph-id={paragraphId}>{text}</p>
            {!focusMode && comments.length > 0 && <button id={`note-mark-${line}`} className="passage-mark" aria-label={`Read ${comments.length} ${comments.length === 1 ? "note" : "notes"} on paragraph ${line}`} aria-expanded={isOpen} aria-controls={isOpen ? `notes-${line}` : undefined} onClick={() => onOpenPopover(line)} data-testid={`margin-dot-line-${line}`}>
              <span className="passage-mark-dots">{readerIds.map(readerId => <i key={readerId} style={readerColorStyle(personas.find(reader => reader.id === readerId)?.avatar_index)} />)}</span><span className="passage-mark-count">{comments.length}</span>
            </button>}
            {isOpen && <PassageNotes line={line} comments={comments} personas={personas} close={() => close(line)} previous={position > 0 ? () => jump(annotated[position - 1]) : null} next={position < annotated.length - 1 ? () => jump(annotated[position + 1]) : null} position={position} count={annotated.length} />}
          </div>;
        })}
      </section>)}
      <footer className="book-colophon"><p>End of manuscript</p><div><button onClick={() => onNavigate("manuscript-start")}><ArrowUp size={14} />Back to the beginning</button><button onClick={onOpenReaders}><MessageSquare size={14} />Open reader notebook</button></div></footer>
    </article>
  </div>;
}
