import { useEffect, useRef, useState } from "react";

import { getChatHistory, sendChatMessage } from "../api";

export default function useChat(notebookId) {
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    if (!notebookId) {
      setMessages([]);
      setError("");
      setSending(false);
      return;
    }

    const loadHistory = async () => {
      try {
        const history = await getChatHistory(notebookId);
        if (!cancelled && mountedRef.current) {
          setMessages(history);
          setError("");
        }
      } catch (err) {
        if (!cancelled && mountedRef.current) {
          setError(err instanceof Error ? err.message : "Failed to load chat history");
        }
      }
    };

    loadHistory();
    return () => {
      cancelled = true;
    };
  }, [notebookId]);

  const send = async (text) => {
    const trimmed = text.trim();
    if (!trimmed || !notebookId || sending) return;

    const optimistic = {
      id: `local-${Date.now()}`,
      role: "user",
      content: trimmed,
      sources_cited: [],
    };

    setMessages((prev) => [...prev, optimistic]);
    setSending(true);
    setError("");

    try {
      const response = await sendChatMessage(notebookId, trimmed);
      if (mountedRef.current) {
        setMessages((prev) => [...prev, response]);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      if (mountedRef.current) {
        setMessages((prev) => [
          ...prev,
          {
            id: `local-error-${Date.now()}`,
            role: "assistant",
            content: message,
            sources_cited: [],
          },
        ]);
        setError(message);
      }
    } finally {
      if (mountedRef.current) setSending(false);
    }
  };

  return { messages, send, sending, error, setMessages };
}
