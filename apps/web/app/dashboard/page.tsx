"use client";

import { useEffect, useState } from "react";

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type MeResponse = {
  email?: string;
};

type Trial = {
  id: string;
  service_name: string;
  end_date?: string | null;
  status?: string;
  days_remaining?: number | null;
  cancel_url?: string | null;
};

type TrialsResponse = {
  trials: Trial[];
};

export default function Dashboard() {
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading"
  );
  const [email, setEmail] = useState<string | null>(null);
  const [trials, setTrials] = useState<Trial[]>([]);
  const [signingOut, setSigningOut] = useState(false);

  const sortedTrials = [...trials].sort((a, b) => {
    const aDays = typeof a.days_remaining === "number" ? a.days_remaining : 10_000;
    const bDays = typeof b.days_remaining === "number" ? b.days_remaining : 10_000;
    return aDays - bDays;
  });

  useEffect(() => {
    let active = true;
    Promise.all([
      fetch(`${apiBase}/me`, { credentials: "include" }),
      fetch(`${apiBase}/trials`, { credentials: "include" })
    ])
      .then(async ([meRes, trialsRes]) => {
        if (!meRes.ok) {
          throw new Error("Not authenticated");
        }
        const meData = (await meRes.json()) as MeResponse;
        let trialsData: Trial[] = [];
        if (trialsRes.ok) {
          const parsed = (await trialsRes.json()) as TrialsResponse;
          trialsData = parsed.trials ?? [];
        }
        return { meData, trialsData };
      })
      .then(({ meData, trialsData }) => {
        if (!active) return;
        setEmail(meData.email ?? null);
        setTrials(trialsData);
        setStatus("ready");
      })
      .catch(() => {
        if (!active) return;
        setStatus("error");
      });

    return () => {
      active = false;
    };
  }, []);

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

  if (status === "loading") {
    return (
      <main className="main">
        <section className="card">
          <div className="meta">Checking your Gmail connection...</div>
        </section>
      </main>
    );
  }

  if (status === "error") {
    return (
      <main className="main">
        <section className="card">
          <div className="meta">
            We could not verify your session. Head back to the home page to
            connect Gmail.
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="main">
      <section className="hero" aria-labelledby="dashboard-title">
        <div className="status">Gmail connected</div>
        <div>
          <button className="cta" onClick={signOutAndSwitch} disabled={signingOut}>
            {signingOut ? "Signing out..." : "Sign Out / Switch Account"}
          </button>
        </div>
        <h1 id="dashboard-title">Inbox is linked.</h1>
        <p>
          {email
            ? `Signed in as ${email}.`
            : "You are signed in and ready to scan your inbox."}
        </p>
      </section>
      <section className="card">
        <div className="meta">
          <div>
            {trials.length > 0
              ? `Detected ${trials.length} trial candidate${trials.length === 1 ? "" : "s"}.`
              : "No trial candidates yet. Run a scan to populate your dashboard."}
          </div>
          <div>
            <a className="cta" href="/scan">
              Scan Inbox
            </a>
          </div>
        </div>
      </section>
      {trials.length > 0 && (
        <section className="card" aria-labelledby="trial-list-title">
          <h2 id="trial-list-title">Detected Trials</h2>
          <ul className="trial-list">
            {sortedTrials.map((trial) => (
              <li key={trial.id} className="trial-item">
                <div className="trial-title">{trial.service_name || "Unknown Service"}</div>
                <div className="trial-meta">
                  <span>
                    End date: {trial.end_date || "Unknown"}
                  </span>
                  <span>
                    Days left:{" "}
                    {typeof trial.days_remaining === "number"
                      ? String(trial.days_remaining)
                      : "Unknown"}
                  </span>
                  <span className={`pill ${trial.status || "unknown"}`}>
                    Status: {trial.status || "unknown"}
                  </span>
                </div>
                {trial.cancel_url && (
                  <a href={trial.cancel_url} target="_blank" rel="noreferrer">
                    Cancel link
                  </a>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
