import { ExternalLink, X } from "lucide-react";

export default function NodePopover({ node, onClose }) {
  if (!node) return null;

  return (
    <div className="pointer-events-auto fixed left-1/2 top-1/2 z-50 w-[min(92vw,360px)] -translate-x-1/2 -translate-y-1/2 rounded-[2rem] border border-[#e0e2e0] bg-white p-6 shadow-[0_16px_50px_rgba(15,23,42,0.14)]">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-medium text-[#1f1f1f]">
            {node.title?.startsWith("http") ? "Article header" : node.title}
          </h3>
          <p className="text-xs text-[#5f6368]">
            {node.source_type} {node.status ? `• ${node.status}` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-8 w-8 items-center justify-center rounded-full transition-colors hover:bg-black/5"
        >
          <X className="h-5 w-5 text-[#444746]" />
        </button>
      </div>

      <div className="space-y-3 text-sm text-[#444746]">
        {node.url ? (() => {
          let hostname = node.url;
          try { hostname = new URL(node.url).hostname; } catch (_) {}
          return (
            <p className="flex gap-2">
              <span className="w-16 shrink-0 font-medium text-[#1f1f1f]">Source:</span>
              <span className="truncate text-[#5f6368]">{hostname}</span>
            </p>
          );
        })() : null}
        {node.summary ? (
          <details className="group">
            <summary className="cursor-pointer font-medium text-[#0b57d0] hover:underline">
              View Summary
            </summary>
            <p className="mt-2 leading-relaxed text-[#444746] group-open:animate-in group-open:fade-in">
              {node.summary}
            </p>
          </details>
        ) : (
          <p className="leading-relaxed text-[#5f6368]">
            {node.content ? node.content.slice(0, 100) + "..." : "This source is still processing."}
          </p>
        )}
      </div>

      {node.url ? (
        <a
          href={node.url}
          target="_blank"
          rel="noreferrer"
          className="mt-5 inline-flex items-center gap-2 rounded-full border border-[#c2e7ff] px-4 py-2 text-sm font-medium text-[#0b57d0] transition-colors hover:bg-blue-50"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Open source
        </a>
      ) : null}
    </div>
  );
}
