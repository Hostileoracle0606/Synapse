import { Loader2, X } from "lucide-react";
import { useState } from "react";

export default function SourceComposer({ open, onClose, onSubmit, isLoading }) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState("webpage");

  if (!open) return null;

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!url.trim()) return;
    onSubmit({
      url: url.trim(),
      title: title.trim() || undefined,
      sourceType,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 px-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-[2rem] border border-[#e0e2e0] bg-white p-6 shadow-[0_20px_50px_rgba(15,23,42,0.16)]">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-medium text-[#1f1f1f]">Add source</h2>
            <p className="text-sm text-[#5f6368]">Manually add a webpage to the notebook.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-full transition-colors hover:bg-black/5"
          >
            <X className="h-5 w-5 text-[#444746]" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            type="url"
            placeholder="https://example.com/source"
            className="w-full rounded-2xl border border-[#e0e2e0] bg-[#f8f9fa] px-4 py-3 text-[15px] outline-none transition-shadow placeholder:text-[#80868b] focus:border-[#c2e7ff] focus:bg-white focus:shadow-[0_0_0_1px_#0b57d0]"
          />
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Optional title"
            className="w-full rounded-2xl border border-[#e0e2e0] bg-[#f8f9fa] px-4 py-3 text-[15px] outline-none transition-shadow placeholder:text-[#80868b] focus:border-[#c2e7ff] focus:bg-white focus:shadow-[0_0_0_1px_#0b57d0]"
          />
          <select
            value={sourceType}
            onChange={(event) => setSourceType(event.target.value)}
            className="w-full rounded-2xl border border-[#e0e2e0] bg-[#f8f9fa] px-4 py-3 text-[15px] outline-none transition-shadow focus:border-[#c2e7ff] focus:bg-white focus:shadow-[0_0_0_1px_#0b57d0]"
          >
            <option value="webpage">Webpage</option>
            <option value="pdf">PDF</option>
          </select>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-full border border-[#e0e2e0] py-3 text-sm font-medium text-[#444746] transition-colors hover:bg-[#f8f9fa]"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!url.trim() || isLoading}
              className="flex flex-1 items-center justify-center gap-2 rounded-full bg-[#0b57d0] py-3 text-sm font-medium text-white transition-colors hover:bg-[#0842a0] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Adding...
                </>
              ) : (
                "Add source"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
