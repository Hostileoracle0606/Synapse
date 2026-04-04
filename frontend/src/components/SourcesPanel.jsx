import { FileText, Globe, Upload } from "lucide-react";

function sourceTone(status) {
  switch (status) {
    case "ready":
      return "bg-[#34a853]";
    case "crawling":
    case "processing":
      return "bg-[#fbbc04] animate-pulse";
    case "error":
      return "bg-[#ea4335]";
    default:
      return "bg-[#c7c9cc]";
  }
}

export default function SourcesPanel({ sources, selectedSourceId, onSelectSource, onAddSource, revealing = false }) {
  return (
    <section className="flex w-full flex-col gap-4 overflow-y-auto rounded-[2rem] bg-white/70 p-4 shadow-sm ring-1 ring-[#e0e2e0] backdrop-blur-sm lg:w-80 lg:bg-transparent lg:p-0 lg:shadow-none lg:ring-0" style={revealing ? { width: 0, opacity: 0, overflow: "hidden" } : { width: undefined, opacity: 1, transition: "width 400ms ease-out, opacity 400ms ease-out" }}>
      <div className="flex items-center justify-between px-1">
        <h2 className="text-sm font-medium text-[#1f1f1f]">
          Sources {sources.length ? <span className="text-[#5f6368]">({sources.length})</span> : null}
        </h2>
        <button
          type="button"
          onClick={onAddSource}
          className="flex h-8 w-8 items-center justify-center rounded-full transition-colors hover:bg-black/5"
        >
          <Upload className="h-5 w-5 text-[#444746]" />
        </button>
      </div>

      <button
        type="button"
        onClick={onAddSource}
        className="group flex items-center gap-4 rounded-3xl border border-transparent bg-white p-4 text-left transition-all hover:border-[#c2e7ff] hover:shadow-md"
      >
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#f0f4f9] transition-colors group-hover:bg-blue-50">
          <Upload className="h-6 w-6 text-[#0b57d0]" />
        </div>
        <div>
          <p className="text-sm font-medium text-[#1f1f1f]">Add source</p>
          <p className="text-xs text-[#5f6368]">Paste a URL or upload later</p>
        </div>
      </button>

      <div className="mt-1 flex flex-col gap-2">
        {sources.length ? (
          sources.map((source) => (
            <button
              key={source.id}
              type="button"
              onClick={() => onSelectSource(source)}
              className={`group rounded-3xl border p-4 text-left transition-all ${
                selectedSourceId === source.id
                  ? "border-[#c2e7ff] bg-blue-50/40 shadow-sm"
                  : "border-transparent bg-white hover:bg-black/[0.02]"
              }`}
            >
              <div className="flex items-start gap-3">
                <div className="mt-1 shrink-0">
                  {source.source_type === "seed" ? (
                    <FileText className="h-5 w-5 text-[#0b57d0]" />
                  ) : (
                    <Globe className="h-5 w-5 text-[#0b57d0]" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="truncate pr-2 text-sm font-medium text-[#1f1f1f]">
                      {source.title?.startsWith("http") ? "Article header" : source.title}
                    </h3>
                    <span className="rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[#5f6368] ring-1 ring-[#e0e2e0]">
                      {source.source_type}
                    </span>
                  </div>
                  <p className="mt-1 flex items-center gap-2 text-xs text-[#5f6368]">
                    <span className={`h-1.5 w-1.5 rounded-full ${sourceTone(source.status)}`} />
                    {source.status === "ready" && source.summary
                      ? source.summary.slice(0, 95)
                      : source.status}
                  </p>

                </div>
              </div>
            </button>
          ))
        ) : (
          <div className="rounded-3xl border border-dashed border-[#dfe3e8] bg-white p-6 text-center text-sm text-[#5f6368]">
            Discovering sources now. Add one manually if you want to expand faster.
          </div>
        )}
      </div>
    </section>
  );
}
