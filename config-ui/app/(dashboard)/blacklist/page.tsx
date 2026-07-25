"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type Rule } from "@/lib/api";
import { RefreshButton } from "@/components/RefreshButton";
import { useRouter } from "next/navigation";

export default function BlacklistPage() {
  const router = useRouter();
  const [items, setItems] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pattern, setPattern] = useState("");

  async function load() {
    setLoading(true);
    try {
      setItems(await api.get<Rule[]>("/api/blacklist"));
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
    if (!pattern.trim()) return;
    try {
      new RegExp(pattern);  // preflight
    } catch {
      setError("pattern is invalid regex");
      return;
    }
    try {
      await api.post("/api/blacklist", { pattern });
      setPattern("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove(id: number) {
    if (!confirm("Remove this blacklist entry?")) return;
    try {
      await api.delete(`/api/rules/${id}`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Blacklist</h1>
        <RefreshButton />
      </div>
      <p className="text-sm text-muted-foreground">
        Blacklist entries are rules with coefficient <code>0</code>: matched URLs
        are removed from results entirely.
      </p>

      <form onSubmit={add} className="flex gap-2">
        <input
          value={pattern}
          onChange={(e) => setPattern(e.target.value)}
          placeholder=".*spam-site\\.example/.*"
          className="flex-1 border border-border rounded px-3 py-2 text-sm bg-background"
        />
        <button className="bg-primary text-primary-foreground rounded px-4 py-2 text-sm">
          Add
        </button>
      </form>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <table className="w-full text-sm border border-border rounded">
        <thead className="bg-muted/50">
          <tr>
            <th className="text-left p-2">ID</th>
            <th className="text-left p-2">Pattern</th>
            <th className="text-right p-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={3} className="p-4 text-muted-foreground">Loading...</td>
            </tr>
          )}
          {!loading &&
            items.map((r) => (
              <tr key={r.id} className="border-t border-border">
                <td className="p-2">{r.id}</td>
                <td className="p-2 font-mono text-xs">{r.pattern}</td>
                <td className="p-2 text-right">
                  <button
                    onClick={() => remove(r.id)}
                    className="underline text-red-600"
                  >
                    delete
                  </button>
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}
