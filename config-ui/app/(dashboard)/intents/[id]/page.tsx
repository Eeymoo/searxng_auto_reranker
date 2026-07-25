"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { api, ApiError, type Intent } from "@/lib/api";

export default function IntentDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  const [intent, setIntent] = useState<Intent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newKeyword, setNewKeyword] = useState("");

  async function load() {
    setLoading(true);
    try {
      setIntent(await api.get<Intent>(`/api/intents/${id}`));
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.push("/login");
      else setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function addKeyword(e: React.FormEvent) {
    e.preventDefault();
    if (!newKeyword.trim() || !intent) return;
    try {
      await api.post(`/api/intents/${id}/keywords`, { keyword: newKeyword });
      setNewKeyword("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function removeKeyword(kwId: number) {
    try {
      await api.delete(`/api/intents/${id}/keywords?id=${kwId}`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (loading) return <p className="text-muted-foreground">Loading...</p>;
  if (!intent)
    return (
      <div>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button onClick={() => router.push("/intents")} className="underline">
          back
        </button>
      </div>
    );

  return (
    <div className="space-y-6">
      <button onClick={() => router.push("/intents")} className="text-sm underline">
        ← back to intents
      </button>
      <div>
        <h1 className="text-xl font-semibold">{intent.name}</h1>
        <p className="text-sm text-muted-foreground">
          priority {intent.priority} · {intent.enabled ? "enabled" : "disabled"}
        </p>
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <section>
        <h2 className="text-sm font-medium mb-2">Keywords</h2>
        <form onSubmit={addKeyword} className="flex gap-2 mb-3">
          <input
            value={newKeyword}
            onChange={(e) => setNewKeyword(e.target.value)}
            placeholder="add a keyword"
            className="flex-1 border border-border rounded px-3 py-2 text-sm bg-background"
          />
          <button className="bg-primary text-primary-foreground rounded px-4 py-2 text-sm">
            Add
          </button>
        </form>
        <ul className="flex flex-wrap gap-2">
          {intent.keywords.map((k) => (
            <li
              key={k.id}
              className="px-2 py-1 border border-border rounded text-sm flex items-center gap-2"
            >
              {k.keyword}
              <button
                onClick={() => removeKeyword(k.id)}
                className="text-red-600"
                aria-label={`remove ${k.keyword}`}
              >
                ×
              </button>
            </li>
          ))}
          {intent.keywords.length === 0 && (
            <li className="text-sm text-muted-foreground">no keywords yet</li>
          )}
        </ul>
        <p className="text-xs text-muted-foreground mt-2">
          Intent-specific rules can be added from the{" "}
          <a
            href={`/rules?intent=${intent.id}`}
            className="underline"
          >
            Rules page
          </a>{" "}
          by setting the Intent ID.
        </p>
      </section>
    </div>
  );
}
