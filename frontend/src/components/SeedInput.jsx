import { ArrowRight, FileText, Link as LinkIcon, Loader2 } from "lucide-react";
import { useState } from "react";

export default function SeedInput({ onSubmit, isLoading, error, initialSeedUrl = "", initialTitle = "" }) {
  const [mode, setMode] = useState("url");
  const [seedUrl, setSeedUrl] = useState(initialSeedUrl);
  const [seedText, setSeedText] = useState("");
  const [title, setTitle] = useState(initialTitle);

  const handleSubmit = (event) => {
    event.preventDefault();
    if (mode === "url" && seedUrl.trim()) {
      onSubmit({ seedUrl: seedUrl.trim(), title: title.trim() || undefined });
      return;
    }
    if (mode === "text" && seedText.trim()) {
      onSubmit({ seedText: seedText.trim(), title: title.trim() || undefined });
    }
  };

  const canSubmit = mode === "url" ? seedUrl.trim() : seedText.trim();

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,rgba(66,133,244,0.12),transparent_40%),linear-gradient(180deg,#f7fafe_0%,#eef3f8_100%)] px-4">
      <div className="w-full max-w-2xl">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-normal tracking-tight text-[#1f1f1f]">
            Synapse Notebook
          </h1>
          <p className="mt-2 text-sm text-[#5f6368]">
            Paste a URL or seed text and let the notebook discover related sources.
          </p>
        </div>

        <div className="rounded-[2rem] border border-[#e0e2e0] bg-white p-6 shadow-[0_16px_40px_rgba(15,23,42,0.08)] sm:p-8">
          <div className="mb-5 flex gap-2">
            <button
              type="button"
              onClick={() => setMode("url")}
              className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                mode === "url"
                  ? "bg-[#0b57d0] text-white"
                  : "bg-[#f0f4f9] text-[#444746] hover:bg-[#e1e3e1]"
              }`}
            >
              <LinkIcon className="h-4 w-4" />
              URL
            </button>
            <button
              type="button"
              onClick={() => setMode("text")}
              className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                mode === "text"
                  ? "bg-[#0b57d0] text-white"
                  : "bg-[#f0f4f9] text-[#444746] hover:bg-[#e1e3e1]"
              }`}
            >
              <FileText className="h-4 w-4" />
              Text
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Notebook title (optional)"
              className="w-full rounded-2xl border border-[#e0e2e0] bg-[#f8f9fa] px-4 py-3 text-[15px] text-[#1f1f1f] outline-none transition-shadow placeholder:text-[#80868b] focus:border-[#c2e7ff] focus:bg-white focus:shadow-[0_0_0_1px_#0b57d0]"
            />

            {mode === "url" ? (
              <input
                type="url"
                value={seedUrl}
                onChange={(event) => setSeedUrl(event.target.value)}
                placeholder="https://example.com/article"
                className="w-full rounded-2xl border border-[#e0e2e0] bg-[#f8f9fa] px-4 py-3 text-[15px] text-[#1f1f1f] outline-none transition-shadow placeholder:text-[#80868b] focus:border-[#c2e7ff] focus:bg-white focus:shadow-[0_0_0_1px_#0b57d0]"
                autoFocus
              />
            ) : (
              <textarea
                value={seedText}
                onChange={(event) => setSeedText(event.target.value)}
                placeholder="Paste notes, an excerpt, or source text"
                rows={7}
                className="w-full resize-none rounded-2xl border border-[#e0e2e0] bg-[#f8f9fa] px-4 py-3 text-[15px] text-[#1f1f1f] outline-none transition-shadow placeholder:text-[#80868b] focus:border-[#c2e7ff] focus:bg-white focus:shadow-[0_0_0_1px_#0b57d0]"
                autoFocus
              />
            )}

            {error ? <p className="text-sm text-[#b3261e]">{error}</p> : null}

            <button
              type="submit"
              disabled={!canSubmit || isLoading}
              className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#0b57d0] py-3.5 text-sm font-medium text-white transition-colors hover:bg-[#0842a0] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Discovering sources...
                </>
              ) : (
                <>
                  Build knowledge base
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
