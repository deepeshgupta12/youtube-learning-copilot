export default async function Home() {
  const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

  let api: any = null;
  let error: string | null = null;

  try {
    const res = await fetch(`${base}/health`, { cache: "no-store" });
    api = await res.json();
  } catch (e: any) {
    error = e?.message || "Failed to call API";
  }

  return (
    <main style={{ padding: 24, fontFamily: "ui-sans-serif, system-ui" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700 }}>YouTube Learning Copilot</h1>
      <p style={{ marginTop: 8 }}>
        Local V0 bootstrap: Web calls API health endpoint.
      </p>

      <section style={{ marginTop: 16 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600 }}>API Status</h2>
        {error ? (
          <pre style={{ marginTop: 8, padding: 12, background: "#f5f5f5" }}>
            Error: {error}
          </pre>
        ) : (
          <pre style={{ marginTop: 8, padding: 12, background: "#f5f5f5" }}>
            {JSON.stringify(api, null, 2)}
          </pre>
        )}
      </section>

      <section style={{ marginTop: 16 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600 }}>Next Steps</h2>
        <ul style={{ marginTop: 8, paddingLeft: 18 }}>
          <li>Docker: Postgres (pgvector) + Redis already scaffolded</li>
          <li>Next: add DB models + job queue + YouTube ingestion pipeline</li>
        </ul>
      </section>
    </main>
  );
}