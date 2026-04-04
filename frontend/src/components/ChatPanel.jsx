import { FileText, Loader2, MessageSquare, Send, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export default function ChatPanel({ messages, onSend, sending, sources, onSelectSource, error, revealing = false }) {
  const [input, setInput] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, sending]);

  const sourcesById = Object.fromEntries((sources || []).map((source) => [source.id, source]));

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!input.trim() || sending) return;
    onSend(input.trim());
    setInput("");
  };

  return (
    <section className="flex w-full flex-col overflow-hidden rounded-[2rem] border border-[#e0e2e0] bg-white shadow-sm lg:w-[380px]" style={revealing ? { width: 0, opacity: 0, overflow: "hidden" } : { width: undefined, opacity: 1, transition: "width 400ms ease-out 80ms, opacity 400ms ease-out 80ms" }}>
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
              <div key={message.id || index} className="flex min-w-0 gap-4">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-50">
                  <Sparkles className="h-4 w-4 text-[#0b57d0]" />
                </div>
                <div className="min-w-0 pt-1 text-[15px] text-[#1f1f1f]">
                  <p className="whitespace-pre-wrap break-words leading-relaxed">{message.content}</p>
                  {message.sources_cited?.length ? (
                    <div className="mt-3 rounded-2xl border border-[#e0e2e0] bg-[#f8f9fa] p-3">
                      <p className="mb-2 flex items-center gap-2 text-xs text-[#5f6368]">
                        <FileText className="h-3.5 w-3.5" />
                        Cited sources
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {message.sources_cited.map((sourceId) => (
                          <button
                            key={sourceId}
                            type="button"
                            onClick={() => onSelectSource?.(sourcesById[sourceId])}
                            className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-[#0b57d0] ring-1 ring-[#c2e7ff] transition-colors hover:bg-blue-50"
                          >
                            {sourcesById[sourceId]?.title || "Source"}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
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
