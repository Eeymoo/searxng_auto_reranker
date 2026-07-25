"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError, type Intent } from "@/lib/api";
import { RefreshButton } from "@/components/RefreshButton";
import { useRouter } from "next/navigation";

export default function IntentsPage() {
  const router = useRouter();
  const [intents, setIntents] = useState<Intent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");

  async function load() {
    setLoading(true);
    try {
      setIntents(await api.get<Intent[]>("/api/intents"));
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
  }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await api.post("/api/intents", { name });
      setName("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Intents</h1>
        <RefreshButton />
      </div>

      <form onSubmit={add} className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="intent name (e.g. gaming)"
          className="flex-1 border border-border rounded px-3 py-2 text-sm bg-background"
        />
        <button className="bg-primary text-primary-foreground rounded px-4 py-2 text-sm">
          Create
        </button>
      </form>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <div className="grid gap-2">
        {loading && <p className="text-muted-foreground">Loading...</p>}
        {!loading &&
          intents.map((i) => (
            <div
              key={i.id}
              className="border border-border rounded p-3 flex justify-between items-center"
            >
              <div>
                <Link
                  href={`/intents/${i.id}`}
                  className="font-medium hover:underline"
                >
                  {i.name}
                </Link>
                <span className="ml-2 text-xs text-muted-foreground">
                  priority {i.priority} · {i.keywords.length} keywords ·{" "}
                  {i.enabled ? "enabled" : "disabled"}
                </span>
              </div>
              <Link href={`/intents/${i.id}`} className="text-sm underline">
                manage
              </Link>
            </div>
          ))}
        {!loading && intents.length === 0 && (
          <p className="text-muted-foreground text-sm">No intents yet.</p>
        )}
      </div>
    </div>
  );
}
