import { useEffect, useRef, useState } from "react";

import { getNotebook } from "../api";

export default function useNotebook(notebookId) {
  const [notebook, setNotebook] = useState(null);
  const [loading, setLoading] = useState(Boolean(notebookId));
  const [error, setError] = useState("");
  const intervalRef = useRef(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (!notebookId) {
      setNotebook(null);
      setError("");
      setLoading(false);
      return;
    }

    let cancelled = false;

    const stopPolling = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };

    const fetchNotebook = async () => {
      try {
        const data = await getNotebook(notebookId);
        if (cancelled || !mountedRef.current) return;

        setNotebook(data);
        setError("");
        setLoading(false);

        if (data.status === "ready" || data.status === "error") {
          stopPolling();
        }
      } catch (err) {
        if (cancelled || !mountedRef.current) return;
        setError(err instanceof Error ? err.message : "Failed to load notebook");
        setLoading(false);
        stopPolling();
      }
    };

    setLoading(true);
    fetchNotebook();
    intervalRef.current = window.setInterval(fetchNotebook, 3000);

    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [notebookId]);

  const refresh = async () => {
    if (!notebookId) return null;
    const data = await getNotebook(notebookId);
    setNotebook(data);
    return data;
  };

  return { notebook, loading, error, refresh };
}
