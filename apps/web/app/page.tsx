const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  const authUrl = `${apiBase}/auth/google/start?redirect=/dashboard`;

  return (
    <main className="main">
      <section className="hero">
        <div className="status">Inbox-powered trial guardian</div>
        <h1>Never get blindsided by a free-trial charge again.</h1>
        <p>
          Tollgate scans your Gmail, finds every trial confirmation and billing
          notice, and gives you a single, living dashboard of what is expiring
          next. One click to connect, zero manual input.
        </p>
        <div>
          <a className="cta" href={authUrl}>
            Sign in with Google
          </a>
        </div>
      </section>
      <section className="card">
        <div className="meta">
          <div>Connect Gmail with read-only access.</div>
          <div>We parse messy trial emails automatically.</div>
          <div>Set a single reminder rule and forget the rest.</div>
        </div>
      </section>
    </main>
  );
}
