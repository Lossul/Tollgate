"use client";

import { useState } from "react";

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type ScanResult = {
  scanned: number;
  created: number;
};

export default function ScanPage() {
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">(
    "idle"
  );
  const [result, setResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runScan = async () => {
    setStatus("loading");
    setError(null);
    try {
      const response = await fetch(`${apiBase}/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ max_results: 50 })
      });
      if (!response.ok) {
        const text = await response.text();
        let message = text || "Scan failed";
        try {
          const parsed = JSON.parse(text) as { detail?: string };
          if (parsed.detail) {
            message = parsed.detail;
          }
        } catch {
          // Ignore JSON parse errors.
        }

        if (
          message.includes("Gmail API has not been used") ||
          message.includes("SERVICE_DISABLED")
        ) {
          message =
            "Gmail API is not enabled for your Google Cloud project yet. Enable the Gmail API in Google Cloud Console, wait a couple minutes, then retry.";
        }
        throw new Error(message);
      }
      const data = (await response.json()) as ScanResult;
      setResult(data);
      setStatus("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
      setStatus("error");
    }
  };

  return (
    <main className="main">
      <section className="hero">
        <div className="status">Scan Inbox</div>
        <h1>Find every trial in your Gmail.</h1>
        <p>
          We will scan your last 50 Gmail messages for trial confirmations and
          billing notices, then populate your dashboard.
        </p>
        <div>
          <button className="cta" onClick={runScan} disabled={status === "loading"}>
            {status === "loading" ? "Scanning..." : "Start Scan"}
          </button>
        </div>
      </section>
      <section className="card">
        <div className="meta">
          {status === "idle" && <div>Ready when you are.</div>}
          {status === "loading" && <div>Scanning Gmail...</div>}
          {status === "done" && (
            <>
              <div>Scanned {result?.scanned ?? 0} messages.</div>
              <div>Added {result?.created ?? 0} trial candidates.</div>
              <div>
                Head back to the dashboard to see the list as we refine parsing.
              </div>
            </>
          )}
          {status === "error" && (
            <div>Scan failed. {error ?? "Please try again."}</div>
          )}
        </div>
      </section>
    </main>
  );
}
