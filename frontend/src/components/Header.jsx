import { Bell, BookOpen, CircleHelp, Plus } from "lucide-react";

export default function Header({ title, status, onAddSource }) {
  return (
    <header className="flex flex-col gap-3 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-100">
          <BookOpen className="h-5 w-5 text-[#0b57d0]" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-normal tracking-tight text-[#1f1f1f]">
              {title || "Synapse Notebook"}
            </h1>
            {status ? (
              <span className="rounded-full bg-white/80 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-[#444746] shadow-sm ring-1 ring-[#e0e2e0]">
                {status}
              </span>
            ) : null}
          </div>
          <p className="text-xs text-[#5f6368]">
            Build a source graph, then ask questions against it.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 text-[#444746]">
        <button
          type="button"
          onClick={onAddSource}
          className="inline-flex h-10 items-center gap-2 rounded-full bg-white px-4 text-sm font-medium shadow-sm ring-1 ring-[#e0e2e0] transition-colors hover:bg-[#f8f9fa]"
        >
          <Plus className="h-4 w-4" />
          Add source
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
    </header>
  );
}
