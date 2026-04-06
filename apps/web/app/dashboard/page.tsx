"use client";

import { useEffect, useState } from "react";

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type MeResponse = {
  email?: string;
};

export default function Dashboard() {
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading"
  );
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetch(`${apiBase}/me`, { credentials: "include" })
      .then(async (res) => {
        if (!res.ok) {
          throw new Error("Not authenticated");
        }
        return (await res.json()) as MeResponse;
      })
      .then((data) => {
        if (!active) return;
        setEmail(data.email ?? null);
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
      <section className="hero">
        <div className="status">Gmail connected</div>
        <h1>Inbox is linked.</h1>
        <p>
          {email
            ? `Signed in as ${email}.`
            : "You are signed in and ready to scan your inbox."}
        </p>
      </section>
      <section className="card">
        <div className="meta">
          <div>Next step: run your first scan.</div>
          <div>We will list trials here once scanning is live.</div>
        </div>
      </section>
    </main>
  );
}
