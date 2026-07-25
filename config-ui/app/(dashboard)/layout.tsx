"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";

const NAV = [
  { href: "/rules", label: "Rules" },
  { href: "/intents", label: "Intents" },
  { href: "/blacklist", label: "Blacklist" },
  { href: "/test", label: "Test" },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();

  async function signOut() {
    try {
      // Clear the HttpOnly cookie server-side (it's not readable from JS).
      await api.post("/api/logout");
    } catch {
      // ignore — cookie may already be gone; redirect anyway
    }
    router.push("/login");
  }

  return (
    <div className="min-h-screen flex">
      <aside className="w-56 shrink-0 border-r border-border bg-muted/30 p-4 flex flex-col">
        <div className="font-semibold text-sm mb-6 px-2">Auto Reranker</div>
        <nav className="flex flex-col gap-1 flex-1">
          {NAV.map((item) => {
            const active = pathname?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  "px-3 py-2 rounded text-sm " +
                  (active
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-muted")
                }
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <button
          onClick={signOut}
          className="mt-4 px-3 py-2 text-left rounded text-sm hover:bg-muted text-muted-foreground"
        >
          Sign out
        </button>
      </aside>
      <main className="flex-1 p-8 overflow-auto">{children}</main>
    </div>
  );
}
