import { Loader2, MessageSquare, Send, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import MarkdownContent from "./MarkdownContent";

// Chat-pane width persisted to localStorage so the user's preference
// survives reloads. Bounds keep the pane usable on common screens — too
// narrow and the markdown wraps awkwardly; too wide and the graph view
// loses too much room.
const CHAT_WIDTH_KEY = "synapse:chatWidth";
const CHAT_WIDTH_MIN = 320;
const CHAT_WIDTH_MAX = 800;
const CHAT_WIDTH_DEFAULT = 380;

function loadStoredWidth() {
  try {
    const raw = window.localStorage.getItem(CHAT_WIDTH_KEY);
    const parsed = parseInt(raw || "", 10);
    if (Number.isFinite(parsed) && parsed >= CHAT_WIDTH_MIN && parsed <= CHAT_WIDTH_MAX) {
      return parsed;
    }
  } catch {
    // localStorage may be unavailable (private browsing); fall through.
  }
  return CHAT_WIDTH_DEFAULT;
}

export default function ChatPanel({
  messages,
  onSend,
  sending,
  sources,
  onSelectSource,
  onCitedSourcesChange,
  error,
  revealing = false,
}) {
  const [input, setInput] = useState("");
  const scrollRef = useRef(null);
  // Map of message id → DOM node, populated via the per-message ref callback.
  // Used to scroll a specific message into view when it arrives.
  const messageRefs = useRef({});
  const lastSeenMessageIdRef = useRef(null);

  // Resizable width state. Drag handle on the left edge of the panel
  // adjusts this value live; it persists to localStorage on pointer-up.
  const [chatWidth, setChatWidth] = useState(loadStoredWidth);
  const [isDragging, setIsDragging] = useState(false);
  const dragStateRef = useRef(null);

  // Track lg+ viewport so we only apply the resizable pixel width on
  // desktop. Below lg, the layout stacks vertically and the chat should
  // span the full row width.
  const [isLargeViewport, setIsLargeViewport] = useState(
    typeof window !== "undefined" && window.innerWidth >= 1024,
  );
  useEffect(() => {
    const update = () => setIsLargeViewport(window.innerWidth >= 1024);
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const handleResizeStart = (event) => {
    event.preventDefault();
    dragStateRef.current = {
      startX: event.clientX,
      startWidth: chatWidth,
    };
    setIsDragging(true);
  };

  useEffect(() => {
    if (!isDragging) return;

    const handleMove = (event) => {
      const drag = dragStateRef.current;
      if (!drag) return;
      // Drag left = wider chat (delta becomes negative; subtract from start).
      const next = Math.max(
        CHAT_WIDTH_MIN,
        Math.min(CHAT_WIDTH_MAX, drag.startWidth - (event.clientX - drag.startX)),
      );
      setChatWidth(next);
    };

    const handleUp = () => {
      setIsDragging(false);
      dragStateRef.current = null;
    };

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [isDragging]);

  // Persist width when dragging ends (separate effect so it doesn't fire
  // during the drag — only at rest).
  useEffect(() => {
    if (isDragging) return;
    try {
      window.localStorage.setItem(CHAT_WIDTH_KEY, String(chatWidth));
    } catch {
      // ignore storage quota / private mode
    }
  }, [isDragging, chatWidth]);

  useEffect(() => {
    if (!messages.length) return;

    const last = messages[messages.length - 1];
    const isNewMessage = last.id && last.id !== lastSeenMessageIdRef.current;
    lastSeenMessageIdRef.current = last.id;

    // When a new assistant response arrives, scroll its first line into view
    // (instead of dumping the user at the very bottom of a long answer).
    // For a freshly-sent user message or the "Thinking…" indicator, fall
    // back to the standard scroll-to-bottom so the user sees their input.
    if (isNewMessage && last.role === "assistant" && messageRefs.current[last.id]) {
      messageRefs.current[last.id].scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }

    // Push the new assistant message's cited sources up to the App so the
    // graph view can highlight those nodes. The "cited sources" pill list
    // that used to live below each message is gone — the highlight on the
    // graph is now the visualisation of which sources informed the answer.
    if (isNewMessage && last.role === "assistant") {
      onCitedSourcesChange?.(Array.isArray(last.sources_cited) ? last.sources_cited : []);
    }
  }, [messages, sending, onCitedSourcesChange]);

  // The chat backend renders [Source N] using only `ready` sources (status
  // ready + sorted by created_at). To make the citation pills line up with
  // those numbers, mirror that filter here. If we passed all sources, an
  // errored source in the middle would shift every subsequent citation.
  const citationSources = (sources || []).filter((s) => s.status === "ready");

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!input.trim() || sending) return;
    onSend(input.trim());
    setInput("");
  };

  return (
    <section
      className="relative flex w-full shrink-0 flex-col overflow-hidden rounded-[2rem] border border-[#e0e2e0] bg-white shadow-sm"
      style={
        revealing
          ? { width: 0, opacity: 0, overflow: "hidden", transition: "width 400ms ease-out 80ms, opacity 400ms ease-out 80ms" }
          : {
              // Mobile keeps it full-width via the `w-full` class.
              // lg+ uses the resizable pixel width.
              width: isLargeViewport ? `${chatWidth}px` : undefined,
              opacity: 1,
              transition: isDragging
                ? "none"
                : "width 300ms ease-out, opacity 400ms ease-out 80ms",
            }
      }
    >
      {/* Resize handle — invisible 6px strip on the left edge that becomes
          a hairline accent on hover/drag. Pointer events are pinned via
          window-level listeners (set up in useEffect) so the drag continues
          even if the cursor leaves the strip during a fast move. */}
      <div
        onPointerDown={handleResizeStart}
        className="absolute left-0 top-0 z-20 hidden h-full w-1.5 cursor-col-resize lg:block"
        aria-label="Resize chat panel"
        role="separator"
        aria-orientation="vertical"
      >
        <div
          className={`h-full w-full transition-colors ${
            isDragging ? "bg-[#0b57d0]/40" : "hover:bg-[#0b57d0]/15"
          }`}
        />
      </div>

      <div className="flex items-center border-b border-[#f0f4f9] px-6 py-5">
        <h2 className="flex items-center gap-2 text-base font-medium text-[#1f1f1f]">
          <MessageSquare className="h-5 w-5 text-[#0b57d0]" />
          Notebook Guide
        </h2>
      </div>

      <div ref={scrollRef} className="no-scrollbar flex-1 overflow-y-auto bg-white p-6">
        <div className="mb-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onSend("Summarize the key ideas across all sources")}
            className="rounded-full bg-[#f0f4f9] px-4 py-2 text-xs font-medium text-[#1f1f1f] transition-colors hover:bg-[#e1e3e1]"
          >
            Summarize sources
          </button>
          <button
            type="button"
            onClick={() => onSend("What are the key themes and gaps?")}
            className="rounded-full bg-[#f0f4f9] px-4 py-2 text-xs font-medium text-[#1f1f1f] transition-colors hover:bg-[#e1e3e1]"
          >
            Key themes
          </button>
        </div>

        {messages.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-[#dfe3e8] bg-[#fafafa] p-5 text-sm text-[#5f6368]">
            Ask anything about the sources in this notebook.
          </div>
        ) : null}

        <div className="mt-4 flex flex-col gap-6">
          {messages.map((message, index) =>
            message.role === "user" ? (
              <div key={message.id || index} className="flex justify-end">
                <div className="max-w-[85%] rounded-3xl rounded-tr-md bg-[#f0f4f9] px-5 py-3 text-[15px] text-[#1f1f1f]">
                  {message.content}
                </div>
              </div>
            ) : (
              <div
                key={message.id || index}
                ref={(el) => {
                  if (message.id) messageRefs.current[message.id] = el;
                }}
                className="flex min-w-0 gap-4 scroll-mt-4"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-50">
                  <Sparkles className="h-4 w-4 text-[#0b57d0]" />
                </div>
                <div className="min-w-0 pt-1 text-[15px] text-[#1f1f1f]">
                  <MarkdownContent
                    text={message.content}
                    sources={citationSources}
                    onSelectSource={onSelectSource}
                  />
                  {/* Cited sources are no longer shown as pills here —
                      instead, the cited nodes get highlighted in the
                      graph view. The change happens via
                      onCitedSourcesChange (called when a new assistant
                      message arrives) which propagates up to App.jsx
                      and into DocumentWeb. */}
                </div>
              </div>
            ),
          )}

          {sending ? (
            <div className="flex gap-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-50">
                <Loader2 className="h-4 w-4 animate-spin text-[#0b57d0]" />
              </div>
              <div className="pt-1 text-sm text-[#5f6368]">Thinking...</div>
            </div>
          ) : null}

          {error ? <p className="text-sm text-[#b3261e]">{error}</p> : null}
        </div>
      </div>

      <div className="border-t border-[#f0f4f9] bg-white p-4">
        <form
          onSubmit={handleSubmit}
          className="relative flex items-end rounded-[24px] bg-[#f0f4f9] px-2 py-1 transition-all focus-within:bg-white focus-within:shadow-[0_0_0_1px_#0b57d0]"
        >
          <textarea
            value={input}
            onChange={(event) => {
              setInput(event.target.value);
              event.target.style.height = 'auto';
              event.target.style.height = Math.min(event.target.scrollHeight, 120) + 'px';
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (input.trim() && !sending) {
                  handleSubmit(e);
                  e.target.style.height = 'auto';
                }
              }
            }}
            rows={1}
            placeholder="Ask about your sources..."
            className="no-scrollbar w-full resize-none overflow-y-auto bg-transparent py-3 pl-4 pr-12 text-[15px] text-[#1f1f1f] outline-none placeholder:text-[#5f6368]"
            style={{ minHeight: "44px" }}
          />
          <button
            type="submit"
            disabled={!input.trim() || sending}
            className="absolute bottom-1 right-2 mb-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#0b57d0] text-white transition-colors hover:bg-[#0842a0] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Send className="h-4 w-4 ml-0.5" />
          </button>
        </form>
      </div>
    </section>
  );
}
