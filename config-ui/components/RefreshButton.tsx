"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";

/**
 * "Refresh now" button. Calls POST /api/refresh which sets the force_reload
 * flag in config_meta; the plugin picks it up on the next search.
 */
export function RefreshButton() {
  const [state, setState] = useState<"idle" | "sending" | "ok" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function onClick() {
    setState("sending");
    setMessage(null);
    try {
      await api.post("/api/refresh");
      setState("ok");
      setMessage("Refresh requested. Plugin will reload on next search.");
    } catch (err) {
      setState("error");
      setMessage(err instanceof ApiError ? err.message : "refresh failed");
    } finally {
      setTimeout(() => setState("idle"), 2500);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={onClick}
        disabled={state === "sending"}
        className="rounded border border-border bg-background px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
      >
        {state === "sending" ? "Sending..." : "Refresh now"}
      </button>
      {message && (
        <span
          role="status"
          className={
            "text-xs " + (state === "error" ? "text-red-600" : "text-muted-foreground")
          }
        >
          {message}
        </span>
      )}
    </div>
  );
}
