"use client";

import { useEffect, useState } from "react";

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type MeResponse = {
  email?: string;
};

type Subscription = {
  id: string;
  service_name: string;
  subscription_type?: string | null;
  billing_amount?: string | null;
  billing_frequency?: string | null;
  end_date?: string | null;
  status?: string;
  days_remaining?: number | null;
  cancel_url?: string | null;
};

type TrialsResponse = {
  trials: Subscription[];
};

function subscriptionLabel(sub: Subscription): string {
  if (sub.subscription_type === "free_trial") return "Free Trial";
  if (sub.subscription_type === "paid_subscription") return "Subscription";
  return "Subscription";
}

function billingBadge(sub: Subscription): string | null {
  if (sub.billing_amount && sub.billing_frequency) {
    return `${sub.billing_amount}/${sub.billing_frequency === "yearly" ? "yr" : sub.billing_frequency === "monthly" ? "mo" : sub.billing_frequency}`;
  }
  if (sub.billing_amount) return sub.billing_amount;
  if (sub.billing_frequency) return sub.billing_frequency;
  return null;
}

export default function Dashboard() {
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading"
  );
  const [email, setEmail] = useState<string | null>(null);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [signingOut, setSigningOut] = useState(false);

  const sorted = [...subscriptions].sort((a, b) => {
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
        if (!meRes.ok) throw new Error("Not authenticated");
        const meData = (await meRes.json()) as MeResponse;
        let trialsData: Subscription[] = [];
        if (trialsRes.ok) {
          const parsed = (await trialsRes.json()) as TrialsResponse;
          trialsData = parsed.trials ?? [];
        }
        return { meData, trialsData };
      })
      .then(({ meData, trialsData }) => {
        if (!active) return;
        setEmail(meData.email ?? null);
        setSubscriptions(trialsData);
        setStatus("ready");
      })
      .catch(() => {
        if (!active) return;
        setStatus("error");
      });

    return () => { active = false; };
  }, []);

  const signOutAndSwitch = async () => {
    try {
      setSigningOut(true);
      await fetch(`${apiBase}/auth/logout`, { method: "POST", credentials: "include" });
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
            We could not verify your session. Head back to the home page to connect Gmail.
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
          <button type="button" className="cta" onClick={signOutAndSwitch} disabled={signingOut}>
            {signingOut ? "Signing out..." : "Sign Out / Switch Account"}
          </button>
        </div>
        <h1 id="dashboard-title">Your subscriptions.</h1>
        <p>
          {email
            ? `Signed in as ${email}.`
            : "You are signed in and ready to scan your inbox."}
        </p>
      </section>
      <section className="card">
        <div className="meta">
          <div>
            {subscriptions.length > 0
              ? `Detected ${subscriptions.length} subscription${subscriptions.length === 1 ? "" : "s"}.`
              : "No subscriptions found yet. Run a scan to detect what you're being charged for."}
          </div>
          <div>
            <a className="cta" href="/scan">
              Scan Inbox
            </a>
          </div>
        </div>
      </section>
      {subscriptions.length > 0 && (
        <section className="card" aria-labelledby="sub-list-title">
          <h2 id="sub-list-title">Detected Subscriptions</h2>
          <ul className="trial-list">
            {sorted.map((sub) => {
              const badge = billingBadge(sub);
              return (
                <li key={sub.id} className="trial-item">
                  <div className="trial-title">
                    {sub.service_name || "Unknown Service"}
                  </div>
                  <div className="trial-meta">
                    <span className={`pill ${sub.subscription_type === "free_trial" ? "expiring_soon" : "active"}`}>
                      {subscriptionLabel(sub)}
                    </span>
                    {badge && <span className="pill">{badge}</span>}
                    {sub.end_date && (
                      <span>
                        {sub.subscription_type === "free_trial" ? "Trial ends" : "Renews"}: {sub.end_date}
                      </span>
                    )}
                    {typeof sub.days_remaining === "number" && sub.end_date && (
                      <span>
                        {sub.days_remaining < 0
                          ? "Expired"
                          : sub.days_remaining === 0
                          ? "Today"
                          : `${sub.days_remaining}d left`}
                      </span>
                    )}
                    {sub.status && (
                      <span className={`pill ${sub.status}`}>
                        {sub.status.replace("_", " ")}
                      </span>
                    )}
                  </div>
                  {sub.cancel_url && (
                    <a href={sub.cancel_url} target="_blank" rel="noreferrer">
                      Manage / Cancel
                    </a>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </main>
  );
}
