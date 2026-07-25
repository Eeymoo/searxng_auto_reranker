import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Auto Reranker Config",
  description: "Manage SearXNG Auto Reranker rules, intents and blacklist",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background text-foreground">{children}</body>
    </html>
  );
}
