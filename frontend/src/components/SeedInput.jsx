import { ArrowRight, Eye, EyeOff, Key, Loader2 } from "lucide-react";
import { useState } from "react";

import { getApiKey, setApiKey } from "../apiKey.js";

// Synapse currently accepts URL seeds only. Text-paste mode existed in
// earlier iterations but adds little value over URL-driven discovery and
// complicates the formation pipeline (the seed has no native title /
// hostname to attribute against). Hidden until/unless we re-enable it.
export default function SeedInput({ onSubmit, isLoading, error, initialSeedUrl = "", initialTitle = "" }) {
  const [seedUrl, setSeedUrl] = useState(initialSeedUrl);
  const [title, setTitle] = useState(initialTitle);
  const [apiKey, setApiKeyState] = useState(getApiKey());
  const [showKey, setShowKey] = useState(false);

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!seedUrl.trim() || !apiKey.trim()) return;
    setApiKey(apiKey);
    onSubmit({ seedUrl: seedUrl.trim(), title: title.trim() || undefined });
  };

  const canSubmit = seedUrl.trim() && apiKey.trim();

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,rgba(66,133,244,0.12),transparent_40%),linear-gradient(180deg,#f7fafe_0%,#eef3f8_100%)] px-4">
      <div className="w-full max-w-2xl">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-normal tracking-tight text-[#1f1f1f]">
            Synapse Notebook
          </h1>
          <p className="mt-2 text-sm text-[#5f6368]">
            Paste a URL and let the notebook discover related sources.
          </p>
        </div>

        <div className="rounded-[2rem] border border-[#e0e2e0] bg-white p-6 shadow-[0_16px_40px_rgba(15,23,42,0.08)] sm:p-8">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="rounded-2xl border border-[#e0e2e0] bg-[#f8f9fa] p-4">
              <label className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-[#5f6368]">
                <Key className="h-3.5 w-3.5" />
                Gemini API Key (BYOK)
              </label>
              <div className="flex items-center gap-2">
                <input
                  type={showKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(event) => setApiKeyState(event.target.value)}
                  placeholder="AIza..."
                  className="flex-1 rounded-xl border border-[#e0e2e0] bg-white px-3 py-2 text-sm font-mono text-[#1f1f1f] outline-none placeholder:text-[#80868b] focus:border-[#0b57d0] focus:shadow-[0_0_0_1px_#0b57d0]"
                  autoComplete="off"
                  spellCheck={false}
                />
                <button
                  type="button"
                  onClick={() => setShowKey((prev) => !prev)}
                  className="rounded-xl border border-[#e0e2e0] bg-white p-2 text-[#5f6368] hover:bg-[#f0f4f9]"
                  aria-label={showKey ? "Hide key" : "Show key"}
                >
                  {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <p className="mt-2 text-xs text-[#5f6368]">
                Stored locally in your browser. Sent only to this Synapse backend, which forwards
                it per-request to Gemini. Get one at{" "}
                <a
                  href="https://aistudio.google.com/apikey"
                  target="_blank"
                  rel="noreferrer"
                  className="text-[#0b57d0] underline"
                >
                  aistudio.google.com/apikey
                </a>
                .
              </p>
            </div>

            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Notebook title (optional)"
              className="w-full rounded-2xl border border-[#e0e2e0] bg-[#f8f9fa] px-4 py-3 text-[15px] text-[#1f1f1f] outline-none transition-shadow placeholder:text-[#80868b] focus:border-[#c2e7ff] focus:bg-white focus:shadow-[0_0_0_1px_#0b57d0]"
            />

            <input
              type="url"
              value={seedUrl}
              onChange={(event) => setSeedUrl(event.target.value)}
              placeholder="https://example.com/article"
              className="w-full rounded-2xl border border-[#e0e2e0] bg-[#f8f9fa] px-4 py-3 text-[15px] text-[#1f1f1f] outline-none transition-shadow placeholder:text-[#80868b] focus:border-[#c2e7ff] focus:bg-white focus:shadow-[0_0_0_1px_#0b57d0]"
              autoFocus
            />

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
