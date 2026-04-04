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
  const { notebook, loading, error, refresh } = useNotebook(notebookId);
  const { messages, send, sending, error: chatError } = useChat(notebookId);
  const revealTimerRef = useRef(null);

  useEffect(() => {
    if (notebookId) {
      window.sessionStorage.setItem("synapse:notebookId", notebookId);
    } else {
      window.sessionStorage.removeItem("synapse:notebookId");
    }
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
    return () => { if (revealTimerRef.current) clearTimeout(revealTimerRef.current); };
  }, []);

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

  const handleFormationReady = useCallback((positions) => {
    setInitialNodePositions(positions);
    setLayoutRevealing(true);
    revealTimerRef.current = setTimeout(() => setLayoutRevealing(false), 500);
  }, []);

  const sources = notebook?.sources || [];
  const statusLabel = notebook?.status ? notebook.status : loading ? "loading" : "";

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

  if (notebook?.status !== "ready" && notebook?.status !== "error") {
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
      <Header
        title={notebook?.title || "Synapse Notebook"}
        status={statusLabel}
        onAddSource={() => setComposerOpen(true)}
      />

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
        />

        <ChatPanel
          messages={messages}
          onSend={send}
          sending={sending}
          sources={sources}
          onSelectSource={setSelectedSource}
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
