"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      // The server validates + sets an HttpOnly cookie in the response.
      const resp = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (resp.status === 401 || resp.status === 400) {
        const body = await resp.json().catch(() => ({ error: "login failed" }));
        throw new Error(body.error || "invalid token");
      }
      if (!resp.ok) {
        throw new Error("login service unavailable");
      }
      router.push("/rules");
    } catch (err) {
      setError((err as Error).message || "login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-muted/30">
      <form
        onSubmit={handleSubmit}
        className="bg-background border border-border rounded-lg p-8 w-full max-w-sm shadow-sm"
      >
        <h1 className="text-xl font-semibold mb-1">Auto Reranker</h1>
        <p className="text-sm text-muted-foreground mb-6">
          Enter your access token to manage rules.
        </p>
        <label className="block text-sm font-medium mb-2">Token</label>
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          autoFocus
          placeholder="••••••••••••"
          className="w-full rounded border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          required
        />
        {error && (
          <p className="mt-3 text-sm text-red-600" role="alert">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={loading || !token}
          className="mt-6 w-full rounded bg-primary text-primary-foreground px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          {loading ? "Verifying..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}
