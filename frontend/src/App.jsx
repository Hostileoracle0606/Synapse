import { useCallback, useEffect, useRef, useState } from "react";

import { addSource, createNotebook, isDemoMode } from "./api";
import ChatPanel from "./components/ChatPanel";
import DocumentWeb from "./components/DocumentWeb";
import FormationScreen from "./components/FormationScreen";
import Header from "./components/Header";
import SeedInput from "./components/SeedInput";
import SourceComposer from "./components/SourceComposer";
import SourcesPanel from "./components/SourcesPanel";
import useChat from "./hooks/useChat";
import useNotebook from "./hooks/useNotebook";

export default function App() {
  const [notebookId, setNotebookId] = useState(() => window.sessionStorage.getItem("synapse:notebookId") || "");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [composerOpen, setComposerOpen] = useState(false);
  const [composerError, setComposerError] = useState("");
  const [composerLoading, setComposerLoading] = useState(false);
  const [selectedSource, setSelectedSource] = useState(null);
  const [initialNodePositions, setInitialNodePositions] = useState(null);
  const [layoutRevealing, setLayoutRevealing] = useState(false);
  // citedSourceIds is the set of source IDs cited by the latest assistant
  // chat response. The graph view uses this to highlight just those nodes
  // (replacing the old "Cited sources" pill list at the bottom of the chat).
  const [citedSourceIds, setCitedSourceIds] = useState([]);
  // "view" gates the formation→main transition. We hold the formation
  // screen for a moment after notebook becomes ready so the done overlay
  // can fade in/out before the main view replaces it.
  const [view, setView] = useState("formation"); // "formation" | "main"
  const initialNotebookStatusRef = useRef(null);
  const { notebook, loading, error, refresh } = useNotebook(notebookId);
  const { messages, send, sending, error: chatError } = useChat(notebookId);
  const revealTimerRef = useRef(null);
  const transitionTimerRef = useRef(null);

  useEffect(() => {
    if (notebookId) {
      window.sessionStorage.setItem("synapse:notebookId", notebookId);
    } else {
      window.sessionStorage.removeItem("synapse:notebookId");
    }
    // Reset transition state for the new notebook.
    initialNotebookStatusRef.current = null;
    setView("formation");
    // Clear any citation highlight carried over from the previous notebook.
    setCitedSourceIds([]);
  }, [notebookId]);

  useEffect(() => {
    if (!notebook?.sources?.length) {
      setSelectedSource(null);
      return;
    }
    setSelectedSource((current) => {
      if (current) {
        return notebook.sources.find((source) => source.id === current.id) || null;
      }
      return null;
    });
  }, [notebook]);

  useEffect(() => {
    return () => {
      // revealTimerRef now holds an rAF id (not a timeout) — see the
      // view→main effect below. Using cancelAnimationFrame for rAF ids
      // is correct; passing a stale timeout id to clearTimeout is also
      // a no-op so this is safe across both code paths.
      if (revealTimerRef.current) {
        try { window.cancelAnimationFrame(revealTimerRef.current); } catch {}
      }
      if (transitionTimerRef.current) clearTimeout(transitionTimerRef.current);
    };
  }, []);

  // Transition state machine: when the notebook flips into ready/error,
  // hold the formation screen for ~1.8s (so the done overlay has time to
  // play), then swap to the main view. If we mounted onto an already-ready
  // notebook (resume from sessionStorage), skip formation entirely.
  useEffect(() => {
    if (!notebook) return;
    const isReady = notebook.status === "ready" || notebook.status === "error";

    if (initialNotebookStatusRef.current === null) {
      initialNotebookStatusRef.current = notebook.status;
      if (isReady) {
        setView("main");
        return;
      }
    }

    if (isReady && view === "formation") {
      transitionTimerRef.current = setTimeout(() => setView("main"), 1800);
    } else if (!isReady && view === "main") {
      // Edge case: notebook went back into processing (re-crawl?). Fall
      // back to formation gracefully.
      setView("formation");
    }
    return () => {
      if (transitionTimerRef.current) {
        clearTimeout(transitionTimerRef.current);
        transitionTimerRef.current = null;
      }
    };
  }, [notebook, view]);

  const handleCreateNotebook = async (payload) => {
    setCreating(true);
    setCreateError("");
    try {
      const notebookResponse = await createNotebook(payload);
      setNotebookId(notebookResponse.id);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create notebook");
    } finally {
      setCreating(false);
    }
  };

  const handleAddSource = async ({ url, title, sourceType }) => {
    if (!notebookId) return;
    setComposerError("");
    setComposerLoading(true);
    try {
      await addSource(notebookId, { url, title, sourceType });
      setComposerOpen(false);
      await refresh();
    } catch (err) {
      setComposerError(err instanceof Error ? err.message : "Failed to add source");
    } finally {
      setComposerLoading(false);
    }
  };

  // FormationScreen calls this when it detects ready/error and captures
  // the simulation's final node positions. We just store them; the actual
  // panel reveal animation fires when the view actually changes to main
  // (see the effect below), not now.
  const handleFormationReady = useCallback((positions) => {
    setInitialNodePositions(positions);
  }, []);

  // Trigger the entry animation for SourcesPanel + ChatPanel exactly when
  // the view becomes main. They're rendered with revealing=true (width 0)
  // for one frame, then revealing flips to false and the panels slide in
  // from their respective edges. Without this two-frame dance, the panels
  // appear at full width with no animation.
  useEffect(() => {
    if (view !== "main") return;
    setLayoutRevealing(true);
    // Two requestAnimationFrame hops ensure the first paint happens with
    // revealing=true (panels at width 0); the second paint flips to
    // revealing=false, which fires the CSS width transition.
    const raf1 = window.requestAnimationFrame(() => {
      const raf2 = window.requestAnimationFrame(() => {
        setLayoutRevealing(false);
      });
      revealTimerRef.current = raf2;
    });
    return () => {
      window.cancelAnimationFrame(raf1);
      if (revealTimerRef.current) {
        window.cancelAnimationFrame(revealTimerRef.current);
      }
    };
  }, [view]);

  const sources = notebook?.sources || [];

  if (!notebookId) {
    return (
      <SeedInput
        onSubmit={handleCreateNotebook}
        isLoading={creating}
        error={createError}
        initialSeedUrl={isDemoMode() ? "https://en.wikipedia.org/wiki/Large_language_model" : ""}
        initialTitle={isDemoMode() ? "How Large Language Models Work" : ""}
      />
    );
  }

  if (view === "formation") {
    return (
      <FormationScreen
        notebook={notebook}
        sources={sources}
        edges={notebook?.edges || []}
        onReady={handleFormationReady}
      />
    );
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[radial-gradient(circle_at_top,rgba(66,133,244,0.08),transparent_40%),linear-gradient(180deg,#f4f8fb_0%,#eef3f8_100%)] text-[#1f1f1f]">
      <Header title={notebook?.title || "Synapse Notebook"} />

      <main className="flex flex-1 flex-col gap-4 px-4 pb-4 lg:flex-row min-h-0 overflow-hidden">
        <SourcesPanel
          sources={sources}
          selectedSourceId={selectedSource?.id}
          onSelectSource={setSelectedSource}
          onAddSource={() => setComposerOpen(true)}
          revealing={layoutRevealing}
        />

        <DocumentWeb
          sources={sources}
          edges={notebook?.edges || []}
          selectedSource={selectedSource}
          onSelectSource={setSelectedSource}
          initialNodePositions={initialNodePositions}
          citedSourceIds={citedSourceIds}
        />

        <ChatPanel
          messages={messages}
          onSend={send}
          sending={sending}
          sources={sources}
          onSelectSource={setSelectedSource}
          onCitedSourcesChange={setCitedSourceIds}
          error={chatError}
          revealing={layoutRevealing}
        />
      </main>

      <SourceComposer
        open={composerOpen}
        onClose={() => { setComposerOpen(false); setComposerError(""); }}
        onSubmit={handleAddSource}
        isLoading={composerLoading}
      />

      {composerError ? (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-full bg-[#b3261e] px-4 py-2 text-sm text-white shadow-lg">
          {composerError}
        </div>
      ) : null}

      {error ? (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-full bg-[#b3261e] px-4 py-2 text-sm text-white shadow-lg">
          {error}
        </div>
      ) : null}

      <style>{`
        .no-scrollbar::-webkit-scrollbar { display: none; }
        .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
      `}</style>
    </div>
  );
}
