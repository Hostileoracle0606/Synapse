import { ChevronDown, ExternalLink, FileText, Globe, MessageCircle, Upload, Youtube } from "lucide-react";
import { useEffect, useRef } from "react";

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

// Per-type icon. Falls back to Globe for any unrecognised type.
function SourceIcon({ source_type }) {
  const className = "h-5 w-5 text-[#0b57d0]";
  switch (source_type) {
    case "seed":
      return <FileText className={className} />;
    case "youtube":
      return <Youtube className={className} />;
    case "pdf":
      return <FileText className={className} />;
    case "social":
      return <MessageCircle className={className} />;
    case "webpage":
    default:
      return <Globe className={className} />;
  }
}

// Show a meaningful label even when the title is still a URL.
function displayTitle(source) {
  const raw = (source.title || "").trim();
  if (!raw) return "Untitled source";
  if (!/^https?:\/\//i.test(raw)) return raw;
  try {
    const u = new URL(raw);
    const cleanPath = u.pathname.replace(/\/$/, "");
    if (!cleanPath || cleanPath === "") return u.hostname;
    const trimmedPath = cleanPath.length > 32 ? cleanPath.slice(0, 32) + "…" : cleanPath;
    return `${u.hostname}${trimmedPath}`;
  } catch {
    return raw.length > 60 ? raw.slice(0, 60) + "…" : raw;
  }
}

function typeBadge(source_type) {
  switch (source_type) {
    case "seed":
      return "seed";
    case "youtube":
      return "video";
    case "pdf":
      return "pdf";
    case "social":
      return "social";
    case "webpage":
    default:
      return "web";
  }
}

function hostnameOf(url) {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// One source rendered as an expandable card. The expanded layout mirrors
// the original NodePopover modal — same content blocks, same typography —
// but inline in the sidebar instead of as a centered overlay. The full
// summary is shown without truncation (live mode produces real summaries,
// not just the demo's short blurbs).
function SourceCard({ source, isSelected, onSelect }) {
  const cardRef = useRef(null);

  // When this card becomes selected (e.g. from clicking a node in the
  // graph), scroll it into view smoothly so the user can see the expanded
  // overview without manually scrolling the sidebar.
  useEffect(() => {
    if (isSelected && cardRef.current) {
      cardRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [isSelected]);

  const handleToggle = () => {
    onSelect(isSelected ? null : source);
  };

  return (
    <div
      ref={cardRef}
      className={`overflow-hidden rounded-3xl border transition-all ${
        isSelected
          ? "border-[#c2e7ff] bg-white shadow-sm"
          : "border-transparent bg-white hover:bg-black/[0.02]"
      }`}
    >
      {/* Collapsed header — same compact list-item shape regardless of
          expanded state, so the list stays scannable when many cards are
          collapsed. */}
      <button
        type="button"
        onClick={handleToggle}
        className="group flex w-full items-start gap-3 p-4 text-left"
        aria-expanded={isSelected}
      >
        <div className="mt-1 shrink-0">
          <SourceIcon source_type={source.source_type} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <h3 className="truncate pr-2 text-sm font-medium text-[#1f1f1f]">
              {displayTitle(source)}
            </h3>
            <span className="rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[#5f6368] ring-1 ring-[#e0e2e0]">
              {typeBadge(source.source_type)}
            </span>
          </div>
          <p className="mt-1 flex items-center gap-2 text-xs text-[#5f6368]">
            <span className={`h-1.5 w-1.5 rounded-full ${sourceTone(source.status)}`} />
            {source.status === "ready" && source.summary
              ? source.summary.slice(0, 95)
              : source.status === "error" && source.error_message
              ? source.error_message.slice(0, 95)
              : source.status}
          </p>
        </div>
        <ChevronDown
          className={`mt-1 h-4 w-4 shrink-0 text-[#5f6368] transition-transform duration-200 ${
            isSelected ? "rotate-180" : "rotate-0"
          }`}
        />
      </button>

      {/* Expanded overview — mirrors NodePopover.jsx's content layout:
          full title heading, type/status subline, "Source:" label with
          hostname, the FULL summary (no truncation), and an "Open source"
          pill at the bottom. */}
      {isSelected ? (
        <div className="border-t border-[#f0f4f9] px-5 pb-5 pt-4">
          {/* Full title + type/status subline (same as popover header) */}
          <h3 className="text-base font-medium leading-snug text-[#1f1f1f]">
            {displayTitle(source)}
          </h3>
          <p className="mt-0.5 text-xs text-[#5f6368]">
            {typeBadge(source.source_type)}
            {source.status ? ` • ${source.status}` : ""}
          </p>

          <div className="mt-3 space-y-3 text-sm text-[#444746]">
            {source.url ? (
              <p className="flex gap-2">
                <span className="w-16 shrink-0 font-medium text-[#1f1f1f]">Source:</span>
                <span className="truncate text-[#5f6368]">{hostnameOf(source.url)}</span>
              </p>
            ) : null}

            {source.summary ? (
              <p className="leading-relaxed text-[#444746]">
                {source.summary}
              </p>
            ) : (
              <p className="leading-relaxed text-[#5f6368]">
                {source.status === "processing" || source.status === "crawling"
                  ? "Reading and analysing this source…"
                  : source.content
                  ? source.content.slice(0, 220) + "…"
                  : "This source is still processing."}
              </p>
            )}
          </div>

          {source.url ? (
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
              className="mt-5 inline-flex items-center gap-2 rounded-full border border-[#c2e7ff] px-4 py-2 text-sm font-medium text-[#0b57d0] transition-colors hover:bg-blue-50"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Open source
            </a>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export default function SourcesPanel({ sources, selectedSourceId, onSelectSource, onAddSource, revealing = false }) {
  const visibleSources = (sources || []).filter((s) => s.status !== "error");

  return (
    <section className="flex w-full flex-col gap-4 overflow-y-auto rounded-[2rem] bg-white/70 p-4 shadow-sm ring-1 ring-[#e0e2e0] backdrop-blur-sm lg:w-80 lg:bg-transparent lg:p-0 lg:shadow-none lg:ring-0" style={revealing ? { width: 0, opacity: 0, overflow: "hidden" } : { width: undefined, opacity: 1, transition: "width 400ms ease-out, opacity 400ms ease-out" }}>
      <div className="flex items-center justify-between px-1">
        <h2 className="text-sm font-medium text-[#1f1f1f]">
          Sources {visibleSources.length ? <span className="text-[#5f6368]">({visibleSources.length})</span> : null}
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
        {visibleSources.length ? (
          visibleSources.map((source) => (
            <SourceCard
              key={source.id}
              source={source}
              isSelected={selectedSourceId === source.id}
              onSelect={onSelectSource}
            />
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
