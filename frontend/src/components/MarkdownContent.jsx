import { Children } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Matches `[Source 1]`, `[Source 1, Source 3]`, `[Source 1, 3, 5]`, etc.
// Captures the FULL bracket so we can split text around it and render each
// referenced source number as its own pill.
const CITATION_RE = /\[Source\s+\d+(?:\s*,\s*(?:Source\s+)?\d+)*\]/g;
const NUMBER_RE = /\d+/g;

// Inline citation pill — rendered in place of "[Source N]" markers when
// the parent supplies a `sources` array. Clicking the pill bubbles up to
// `onSelectSource` so the sidebar's matching card expands and scrolls
// into view.
function CitationPill({ index, sources, onSelectSource }) {
  const source = sources?.[index] || null;
  const tooltip = source?.title || `Source ${index + 1}`;
  const handle = (event) => {
    event.preventDefault();
    if (source) onSelectSource?.(source);
  };
  return (
    <button
      type="button"
      onClick={handle}
      title={tooltip}
      className="mx-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[#e8f0fe] px-1.5 align-text-bottom text-[11px] font-medium text-[#0b57d0] transition-colors hover:bg-[#d2e3fc]"
    >
      {index + 1}
    </button>
  );
}

// Walk a children array (which may contain strings + React elements) and
// replace any `[Source N…]` substrings inside string leaves with citation
// pills. Non-string children pass through unchanged. This lets us add
// citation rendering at the text-leaf level without rewriting the entire
// markdown AST.
function withCitations(children, sources, onSelectSource) {
  if (children == null) return children;
  if (!sources || !sources.length) return children;

  const wrapString = (text, keyPrefix) => {
    const out = [];
    let lastIndex = 0;
    let match;
    let bracketKey = 0;

    CITATION_RE.lastIndex = 0;
    while ((match = CITATION_RE.exec(text)) !== null) {
      if (match.index > lastIndex) {
        out.push(text.slice(lastIndex, match.index));
      }
      // Pull every number out of the bracket so [Source 1, 3, 5] becomes
      // three separate pills.
      const nums = match[0].match(NUMBER_RE) || [];
      nums.forEach((numStr, j) => {
        const idx = parseInt(numStr, 10) - 1;
        out.push(
          <CitationPill
            key={`${keyPrefix}-cite-${bracketKey}-${j}`}
            index={idx}
            sources={sources}
            onSelectSource={onSelectSource}
          />,
        );
      });
      lastIndex = match.index + match[0].length;
      bracketKey += 1;
    }
    if (lastIndex < text.length) {
      out.push(text.slice(lastIndex));
    }
    return out.length === 1 && typeof out[0] === "string" ? out[0] : out;
  };

  // Children can be a string, a single element, or an array of mixed.
  const arr = Children.toArray(children);
  const transformed = arr.map((child, i) => {
    if (typeof child === "string") {
      const wrapped = wrapString(child, `c-${i}`);
      return Array.isArray(wrapped) ? wrapped : wrapped;
    }
    return child;
  });
  // Flatten any nested arrays so React renders the keys cleanly.
  return transformed.flat();
}

function buildComponents({ sources, onSelectSource }) {
  // Helper that wraps the children of a given element with citation pills.
  // We only override the components that commonly contain narrative text;
  // headings and code blocks intentionally pass through unchanged.
  const wrap = (children) => withCitations(children, sources, onSelectSource);

  return {
    h1: ({ children }) => (
      <h1 className="mb-3 mt-5 text-lg font-semibold text-[#1f1f1f] first:mt-0">{children}</h1>
    ),
    h2: ({ children }) => (
      <h2 className="mb-2 mt-4 text-base font-semibold text-[#1f1f1f] first:mt-0">{children}</h2>
    ),
    h3: ({ children }) => (
      <h3 className="mb-2 mt-4 text-[15px] font-semibold text-[#1f1f1f] first:mt-0">{children}</h3>
    ),
    p: ({ children }) => (
      <p className="mb-3 leading-relaxed text-[#1f1f1f] last:mb-0">{wrap(children)}</p>
    ),
    strong: ({ children }) => (
      <strong className="font-semibold text-[#1f1f1f]">{wrap(children)}</strong>
    ),
    em: ({ children }) => <em className="italic text-[#1f1f1f]">{wrap(children)}</em>,
    ul: ({ children }) => (
      <ul className="mb-3 ml-5 list-disc space-y-2 text-[#1f1f1f] last:mb-0">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="mb-3 ml-5 list-decimal space-y-2 text-[#1f1f1f] last:mb-0">{children}</ol>
    ),
    li: ({ children }) => (
      <li className="leading-relaxed [&>p]:mb-1">{wrap(children)}</li>
    ),
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="text-[#0b57d0] underline decoration-[#c2dbff] underline-offset-2 hover:decoration-[#0b57d0]"
      >
        {children}
      </a>
    ),
    blockquote: ({ children }) => (
      <blockquote className="my-3 border-l-2 border-[#c2dbff] pl-3 italic text-[#444746]">
        {children}
      </blockquote>
    ),
    code: ({ inline, className, children, ...props }) => {
      if (inline) {
        return (
          <code
            className="rounded bg-[#f0f4f9] px-1.5 py-0.5 font-mono text-[13px] text-[#1f1f1f]"
            {...props}
          >
            {children}
          </code>
        );
      }
      return (
        <code className={`font-mono text-[13px] leading-relaxed ${className || ""}`} {...props}>
          {children}
        </code>
      );
    },
    pre: ({ children }) => (
      <pre className="my-3 overflow-x-auto rounded-2xl border border-[#e0e2e0] bg-[#f8f9fa] p-4 text-[13px] leading-relaxed">
        {children}
      </pre>
    ),
    hr: () => <hr className="my-4 border-[#f0f4f9]" />,
    table: ({ children }) => (
      <div className="my-3 overflow-x-auto rounded-2xl border border-[#e0e2e0]">
        <table className="w-full border-collapse text-sm">{children}</table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-[#f8f9fa]">{children}</thead>,
    th: ({ children }) => (
      <th className="border-b border-[#e0e2e0] px-3 py-2 text-left font-semibold text-[#1f1f1f]">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="border-b border-[#f0f4f9] px-3 py-2 align-top text-[#1f1f1f]">{wrap(children)}</td>
    ),
  };
}

export default function MarkdownContent({ text, sources, onSelectSource }) {
  if (!text) return null;
  const components = buildComponents({ sources, onSelectSource });
  return (
    <div className="break-words text-[15px]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
