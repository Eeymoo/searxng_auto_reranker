"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type Rule } from "@/lib/api";
import { RefreshButton } from "@/components/RefreshButton";
import {
  COEFFICIENT_MAX,
  COEFFICIENT_MIN,
} from "@/lib/validation";
import { useRouter } from "next/navigation";

interface FormState {
  pattern: string;
  coefficient: string;
  priority: string;
  intent_id: string;
  enabled: boolean;
  description: string;
}

const EMPTY: FormState = {
  pattern: "",
  coefficient: "1.0",
  priority: "100",
  intent_id: "",
  enabled: true,
  description: "",
};

export default function RulesPage() {
  const router = useRouter();
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [formError, setFormError] = useState<Record<string, string>>({});

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setRules(await api.get<Rule[]>("/api/rules"));
    } catch (err) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  }

  function handleError(err: unknown) {
    if (err instanceof ApiError && err.status === 401) {
      router.push("/login");
    } else {
      setError(err instanceof Error ? err.message : "unknown error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --------------------------------------------------------------- //
  function validate(f: FormState): Record<string, string> {
    const e: Record<string, string> = {};
    if (!f.pattern.trim()) e.pattern = "pattern is required";
    else {
      try {
        new RegExp(f.pattern);
      } catch {
        e.pattern = "pattern is invalid regex";
      }
    }
    const coeff = Number(f.coefficient);
    if (Number.isNaN(coeff)) e.coefficient = "coefficient must be a number";
    else if (coeff < COEFFICIENT_MIN || coeff > COEFFICIENT_MAX)
      e.coefficient = `coefficient must be between ${COEFFICIENT_MIN} and ${COEFFICIENT_MAX}`;
    const prio = Number(f.priority);
    if (!Number.isInteger(prio)) e.priority = "priority must be an integer";
    if (f.intent_id && !Number.isInteger(Number(f.intent_id)))
      e.intent_id = "intent_id must be an integer";
    return e;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validate(form);
    setFormError(errs);
    if (Object.keys(errs).length) return;

    const payload = {
      pattern: form.pattern,
      coefficient: Number(form.coefficient),
      priority: Number(form.priority),
      intent_id: form.intent_id ? Number(form.intent_id) : null,
      enabled: form.enabled,
      description: form.description || null,
    };
    try {
      if (editing !== null) {
        await api.patch(`/api/rules/${editing}`, payload);
      } else {
        await api.post("/api/rules", payload);
      }
      setForm(EMPTY);
      setEditing(null);
      await load();
    } catch (err) {
      handleError(err);
    }
  }

  function startEdit(r: Rule) {
    setEditing(r.id);
    setForm({
      pattern: r.pattern,
      coefficient: String(r.coefficient),
      priority: String(r.priority),
      intent_id: r.intent_id === null ? "" : String(r.intent_id),
      enabled: r.enabled,
      description: r.description ?? "",
    });
    setFormError({});
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function remove(id: number) {
    if (!confirm("Delete this rule?")) return;
    try {
      await api.delete(`/api/rules/${id}`);
      await load();
    } catch (err) {
      handleError(err);
    }
  }

  // --------------------------------------------------------------- //
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Rules</h1>
        <RefreshButton />
      </div>

      <form
        onSubmit={handleSubmit}
        className="border border-border rounded-lg p-4 bg-background space-y-3"
      >
        <div className="text-sm font-medium">
          {editing !== null ? `Editing rule #${editing}` : "Create rule"}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Pattern (regex)" error={formError.pattern}>
            <input
              value={form.pattern}
              onChange={(e) => setForm({ ...form, pattern: e.target.value })}
              placeholder=".*\\.gov\\.cn/.*"
              className="input"
            />
          </Field>
          <Field label={`Coefficient (${COEFFICIENT_MIN}–${COEFFICIENT_MAX})`} error={formError.coefficient}>
            <input
              value={form.coefficient}
              onChange={(e) => setForm({ ...form, coefficient: e.target.value })}
              placeholder="1.0"
              className="input"
            />
          </Field>
          <Field label="Priority (smaller = higher)" error={formError.priority}>
            <input
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
              className="input"
            />
          </Field>
          <Field label="Intent ID (optional)" error={formError.intent_id}>
            <input
              value={form.intent_id}
              onChange={(e) => setForm({ ...form, intent_id: e.target.value })}
              placeholder="blank = generic"
              className="input"
            />
          </Field>
        </div>
        <Field label="Description (optional)">
          <input
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            className="input"
          />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
          />
          enabled
        </label>
        <div className="flex gap-2">
          <button type="submit" className="btn-primary">
            {editing !== null ? "Save" : "Create"}
          </button>
          {editing !== null && (
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setForm(EMPTY);
                setFormError({});
              }}
              className="btn-secondary"
            >
              Cancel
            </button>
          )}
        </div>
      </form>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <div className="border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="text-left p-2">ID</th>
              <th className="text-left p-2">Pattern</th>
              <th className="text-right p-2">Coeff</th>
              <th className="text-right p-2">Prio</th>
              <th className="text-left p-2">Intent</th>
              <th className="text-center p-2">On</th>
              <th className="text-right p-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} className="p-4 text-muted-foreground">
                  Loading...
                </td>
              </tr>
            )}
            {!loading &&
              rules.map((r) => (
                <tr key={r.id} className="border-t border-border">
                  <td className="p-2">{r.id}</td>
                  <td className="p-2 font-mono text-xs">{r.pattern}</td>
                  <td className="p-2 text-right">{r.coefficient}</td>
                  <td className="p-2 text-right">{r.priority}</td>
                  <td className="p-2">{r.intent_id ?? "—"}</td>
                  <td className="p-2 text-center">{r.enabled ? "✓" : ""}</td>
                  <td className="p-2 text-right space-x-2">
                    <button onClick={() => startEdit(r)} className="link">
                      edit
                    </button>
                    <button onClick={() => remove(r.id)} className="link text-red-600">
                      delete
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      <style jsx>{`
        .input {
          width: 100%;
          border: 1px solid hsl(var(--border));
          background: hsl(var(--background));
          border-radius: 4px;
          padding: 6px 10px;
          font-size: 14px;
        }
        .btn-primary {
          background: hsl(var(--primary));
          color: hsl(var(--primary-foreground));
          padding: 6px 16px;
          border-radius: 4px;
          font-size: 14px;
        }
        .btn-secondary {
          border: 1px solid hsl(var(--border));
          padding: 6px 16px;
          border-radius: 4px;
          font-size: 14px;
        }
        .link {
          text-decoration: underline;
          font-size: 14px;
        }
      `}</style>
    </div>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-xs text-muted-foreground mb-1">{label}</span>
      {children}
      {error && <span className="block text-xs text-red-600 mt-1">{error}</span>}
    </label>
  );
}
