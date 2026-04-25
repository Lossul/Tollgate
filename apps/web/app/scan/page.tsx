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
  const [signingOut, setSigningOut] = useState(false);

  const runScan = async () => {
    setStatus("loading");
    setError(null);
    try {
      const response = await fetch(`${apiBase}/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ max_results: 200 })
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

  const signOutAndSwitch = async () => {
    try {
      setSigningOut(true);
      await fetch(`${apiBase}/auth/logout`, {
        method: "POST",
        credentials: "include"
      });
    } finally {
      window.location.href = "/";
    }
  };

  return (
    <main className="main" aria-busy={status === "loading"}>
      <section className="hero" aria-labelledby="scan-title">
        <div className="status" aria-live="polite">
          Scan Inbox
        </div>
        <div>
          <a href="/dashboard">Back to Dashboard</a>
        </div>
        <div>
          <button className="cta" onClick={signOutAndSwitch} disabled={signingOut}>
            {signingOut ? "Signing out..." : "Sign Out / Switch Account"}
          </button>
        </div>
        <h1 id="scan-title">Find every trial in your Gmail.</h1>
        <p>
          We will scan up to 200 Gmail messages for trial confirmations and
          billing notices, then populate your dashboard.
        </p>
        <div>
          <button
            className="cta"
            onClick={runScan}
            disabled={status === "loading"}
            aria-label="Start inbox scan"
          >
            {status === "loading" ? "Scanning..." : "Start Scan"}
          </button>
        </div>
      </section>
      <section className="card" aria-live="polite" aria-atomic="true">
        <div className="meta" role={status === "error" ? "alert" : "status"}>
          {status === "idle" && <div>Ready when you are.</div>}
          {status === "loading" && <div>Scanning Gmail...</div>}
          {status === "done" && (
            <>
              <div>Scanned {result?.scanned ?? 0} messages.</div>
              <div>Added {result?.created ?? 0} trial candidates.</div>
              <div>
                Head back to the dashboard to see the list as we refine parsing.
              </div>
              <div>
                <a href="/dashboard">Go to Dashboard</a>
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
