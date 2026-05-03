import { Bell, BookOpen, CircleHelp, Key } from "lucide-react";
import { useState } from "react";

import { getApiKey, maskApiKey, setApiKey } from "../apiKey.js";

export default function Header({ title }) {
  const [keyValue, setKeyValue] = useState(getApiKey());
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(keyValue);

  const openEditor = () => {
    setDraft(keyValue);
    setEditing(true);
  };

  const saveKey = () => {
    setApiKey(draft);
    setKeyValue(draft);
    setEditing(false);
  };

  const clearKey = () => {
    setApiKey("");
    setKeyValue("");
    setDraft("");
    setEditing(false);
  };

  return (
    <header className="flex flex-col gap-3 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-100">
          <BookOpen className="h-5 w-5 text-[#0b57d0]" />
        </div>
        <div>
          <h1 className="text-xl font-normal tracking-tight text-[#1f1f1f]">
            {title || "Synapse Notebook"}
          </h1>
          <p className="text-xs text-[#5f6368]">
            Build a source graph, then ask questions against it.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 text-[#444746]">
        {/* API key chip — sits in the slot the "Add source" button used
            to occupy. Color shifts on key state: blue when configured,
            red when missing so the user notices before sending requests. */}
        <button
          type="button"
          onClick={openEditor}
          className={`inline-flex h-10 items-center gap-2 rounded-full px-4 text-sm font-medium shadow-sm ring-1 transition-colors ${
            keyValue
              ? "bg-white text-[#0b57d0] ring-[#c2dbff] hover:bg-[#f0f6ff]"
              : "bg-[#fdecea] text-[#b3261e] ring-[#f4c2bd] hover:bg-[#f8d7d3]"
          }`}
          title={keyValue ? "Gemini key set — click to change" : "No Gemini key — click to add"}
        >
          <Key className="h-4 w-4" />
          {keyValue ? maskApiKey(keyValue) : "Set Gemini key"}
        </button>
        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center rounded-full transition-colors hover:bg-black/5"
        >
          <CircleHelp className="h-5 w-5" />
        </button>
        <button
          type="button"
          className="relative flex h-10 w-10 items-center justify-center rounded-full transition-colors hover:bg-black/5"
        >
          <Bell className="h-5 w-5" />
          <span className="absolute right-2 top-2 h-2 w-2 rounded-full border border-[#f0f4f9] bg-[#b3261e]" />
        </button>
        <button
          type="button"
          className="ml-1 flex h-8 w-8 items-center justify-center rounded-full bg-[#0b57d0] text-sm font-medium text-white"
        >
          U
        </button>
      </div>

      {editing ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={() => setEditing(false)}>
          <div
            className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 className="mb-1 flex items-center gap-2 text-lg font-medium text-[#1f1f1f]">
              <Key className="h-5 w-5 text-[#0b57d0]" />
              Gemini API Key
            </h2>
            <p className="mb-4 text-xs text-[#5f6368]">
              Stored locally in your browser. Sent only to this Synapse backend, which forwards it
              per-request to Gemini.
            </p>
            <input
              type="password"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="AIza..."
              className="w-full rounded-xl border border-[#e0e2e0] bg-[#f8f9fa] px-3 py-2 font-mono text-sm outline-none focus:border-[#0b57d0] focus:bg-white focus:shadow-[0_0_0_1px_#0b57d0]"
              autoComplete="off"
              spellCheck={false}
              autoFocus
            />
            <div className="mt-4 flex justify-between gap-2">
              <button
                type="button"
                onClick={clearKey}
                className="rounded-full px-4 py-2 text-sm text-[#b3261e] hover:bg-[#fdecea]"
              >
                Clear
              </button>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setEditing(false)}
                  className="rounded-full px-4 py-2 text-sm text-[#444746] hover:bg-[#f0f4f9]"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={saveKey}
                  className="rounded-full bg-[#0b57d0] px-4 py-2 text-sm font-medium text-white hover:bg-[#0842a0]"
                >
                  Save
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </header>
  );
}
