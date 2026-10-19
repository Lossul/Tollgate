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

type Summary = {
  monthly_total: number;
  yearly_total: number;
  paid_counted: number;
  paid_unpriced: number;
  trials_active: number;
  trials_unpriced: number;
  trial_monthly_exposure: number;
  refund_count: number;
  refunds_pending: number;
  refund_amount: number;
};

type TrialsResponse = {
  trials: Subscription[];
  summary?: Summary;
};

type Draft = {
  kind: "cancel" | "refund";
  subject: string;
  body: string;
};

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD"
});

function isRefundRecord(sub: Subscription): boolean {
  return (
    sub.subscription_type === "refund" ||
    sub.subscription_type === "duplicate_charge"
  );
}

function subscriptionLabel(sub: Subscription): string {
  if (sub.subscription_type === "free_trial") return "Free Trial";
  if (sub.subscription_type === "refund") return "Refund";
  if (sub.subscription_type === "duplicate_charge") return "Possible duplicate charge";
  return "Subscription";
}

function statusLabel(status: string): string {
  if (status === "refund_pending") return "refund pending";
  if (status === "refund_received") return "refund received";
  if (status === "billing_issue") return "needs follow-up";
  return status.replace("_", " ");
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
  const [items, setItems] = useState<Subscription[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [signingOut, setSigningOut] = useState(false);
  const [draftFor, setDraftFor] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const subscriptions = items.filter((item) => !isRefundRecord(item));
  const refunds = items.filter(isRefundRecord);

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
        let summaryData: Summary | null = null;
        if (trialsRes.ok) {
          const parsed = (await trialsRes.json()) as TrialsResponse;
          trialsData = parsed.trials ?? [];
          summaryData = parsed.summary ?? null;
        }
        return { meData, trialsData, summaryData };
      })
      .then(({ meData, trialsData, summaryData }) => {
        if (!active) return;
        setEmail(meData.email ?? null);
        setItems(trialsData);
        setSummary(summaryData);
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

  const openDraft = async (id: string, kind?: "cancel" | "refund") => {
    setDraftFor(id);
    setDraft(null);
    setDraftError(null);
    setCopied(false);
    try {
      const res = await fetch(`${apiBase}/trials/${id}/draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(kind ? { kind } : {})
      });
      if (!res.ok) throw new Error("Could not build the draft");
      setDraft((await res.json()) as Draft);
    } catch (err) {
      setDraftError(err instanceof Error ? err.message : "Could not build the draft");
    }
  };

  const closeDraft = () => {
    setDraftFor(null);
    setDraft(null);
    setDraftError(null);
  };

  const copyDraft = async () => {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const renderDraftPanel = (id: string) => {
    if (draftFor !== id) return null;
    return (
      <div className="draft-panel" role="region" aria-label="Email draft">
        {draftError && <div role="alert">{draftError}</div>}
        {!draft && !draftError && <div>Building draft...</div>}
        {draft && (
          <>
            <div className="draft-subject">
              <strong>Subject:</strong> {draft.subject}
            </div>
            <textarea
              className="draft-body"
              readOnly
              value={draft.body}
              aria-label="Email body"
              rows={12}
            />
            <div className="draft-note">
              Fill in anything in [BRACKETS] before sending.
            </div>
            <div className="draft-actions">
              <button type="button" className="cta" onClick={copyDraft}>
                {copied ? "Copied" : "Copy email"}
              </button>
              <button type="button" className="link-button" onClick={closeDraft}>
                Close
              </button>
            </div>
          </>
        )}
      </div>
    );
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

      {summary && items.length > 0 && (
        <section className="card" aria-labelledby="summary-title">
          <h2 id="summary-title">What you are paying</h2>
          <div className="summary-grid">
            <div className="stat">
              <div className="stat-value">{money.format(summary.monthly_total)}</div>
              <div className="stat-label">per month</div>
            </div>
            <div className="stat">
              <div className="stat-value">{money.format(summary.yearly_total)}</div>
              <div className="stat-label">per year</div>
            </div>
            {summary.trials_active > 0 && (
              <div className="stat">
                <div className="stat-value">{summary.trials_active}</div>
                <div className="stat-label">
                  active free trial{summary.trials_active === 1 ? "" : "s"}
                  {summary.trial_monthly_exposure > 0 &&
                    ` (${money.format(summary.trial_monthly_exposure)}/mo if they convert)`}
                </div>
              </div>
            )}
            {summary.refund_count > 0 && (
              <div className="stat">
                <div className="stat-value">{summary.refund_count}</div>
                <div className="stat-label">
                  refund / billing email{summary.refund_count === 1 ? "" : "s"}
                  {summary.refund_amount > 0 &&
                    ` (${money.format(summary.refund_amount)} in refunds)`}
                </div>
              </div>
            )}
          </div>
          {summary.paid_unpriced > 0 && (
            <div className="draft-note">
              {summary.paid_unpriced} subscription{summary.paid_unpriced === 1 ? "" : "s"} had no
              price we could read, so {summary.paid_unpriced === 1 ? "it is" : "they are"} not
              included in these totals.
            </div>
          )}
        </section>
      )}

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
                        {statusLabel(sub.status)}
                      </span>
                    )}
                  </div>
                  <div className="trial-actions">
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => openDraft(sub.id, "cancel")}
                    >
                      Draft cancel email
                    </button>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => openDraft(sub.id, "refund")}
                    >
                      Draft refund request
                    </button>
                    {sub.cancel_url && (
                      <a href={sub.cancel_url} target="_blank" rel="noreferrer">
                        Manage / Cancel
                      </a>
                    )}
                  </div>
                  {renderDraftPanel(sub.id)}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {refunds.length > 0 && (
        <section className="card" aria-labelledby="refund-list-title">
          <h2 id="refund-list-title">Refunds &amp; billing issues</h2>
          <ul className="trial-list">
            {refunds.map((item) => (
              <li key={item.id} className="trial-item">
                <div className="trial-title">
                  {item.service_name || "Unknown Service"}
                </div>
                <div className="trial-meta">
                  <span className={`pill ${item.status ?? ""}`}>
                    {subscriptionLabel(item)}
                  </span>
                  {item.billing_amount && <span className="pill">{item.billing_amount}</span>}
                  {item.status && <span>{statusLabel(item.status)}</span>}
                </div>
                <div className="trial-actions">
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => openDraft(item.id)}
                  >
                    {item.subscription_type === "duplicate_charge"
                      ? "Draft dispute email"
                      : "Draft follow-up email"}
                  </button>
                </div>
                {renderDraftPanel(item.id)}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
