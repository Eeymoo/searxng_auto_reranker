"use client";

import { useState } from "react";
import { api, ApiError, type TestResult } from "@/lib/api";
import { useRouter } from "next/navigation";

export default function TestPage() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.post<TestResult>("/api/test", { url, query }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.push("/login");
      else setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Test a URL</h1>
      <p className="text-sm text-muted-foreground">
        Preview which rule a URL would match, the coefficient that applies, and
        whether it would be dropped. Optional query triggers intent routing.
      </p>

      <form onSubmit={run} className="space-y-3 max-w-xl">
        <label className="block">
          <span className="block text-xs text-muted-foreground mb-1">URL</span>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.example.gov.cn/news"
            className="w-full border border-border rounded px-3 py-2 text-sm bg-background"
          />
        </label>
        <label className="block">
          <span className="block text-xs text-muted-foreground mb-1">
            Query (optional)
          </span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="买 steam 游戏"
            className="w-full border border-border rounded px-3 py-2 text-sm bg-background"
          />
        </label>
        <button
          disabled={loading || !url}
          className="bg-primary text-primary-foreground rounded px-4 py-2 text-sm disabled:opacity-50"
        >
          {loading ? "Testing..." : "Test"}
        </button>
      </form>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      {result && (
        <div className="border border-border rounded p-4 max-w-xl space-y-2 text-sm">
          <div>
            <span className="text-muted-foreground">Coefficient:</span>{" "}
            <strong>{result.coefficient}</strong>
          </div>
          <div>
            <span className="text-muted-foreground">Dropped:</span>{" "}
            <strong>{result.dropped ? "yes" : "no"}</strong>
          </div>
          <div>
            <span className="text-muted-foreground">Evaluated rules:</span>{" "}
            {result.evaluated_rule_count}
          </div>
          {result.matched_rule ? (
            <div>
              <span className="text-muted-foreground">Matched rule:</span>{" "}
              <code className="font-mono text-xs">
                #{result.matched_rule.id} {result.matched_rule.pattern}
              </code>
            </div>
          ) : (
            <div className="text-muted-foreground">
              No rule matched (coefficient defaults to 1.0).
            </div>
          )}
        </div>
      )}
    </div>
  );
}
