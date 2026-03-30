import { useState } from "react";
// import { Dashboard } from "./Dashboard";

type HomeProps = {
  onLogout: () => void;
};

type FetchErrorDetail = {
  step?: string;
  stderr?: string;
  stdout?: string;
};

export function Home({ onLogout }: HomeProps) {
  const user = JSON.parse(localStorage.getItem("user")!);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // const [dashboardRevision, setDashboardRevision] = useState(0);

  async function handleFetchData() {
    setLoading(true);
    setMessage(null);
    setError(null);

    const controller = new AbortController();
    const timeoutMs = 60 * 60 * 1000;
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

    try {
      const res = await fetch("/api/fetch-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: user.lastfmUsername }),
        signal: controller.signal,
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        const detail = data.detail as FetchErrorDetail | string | undefined;
        if (typeof detail === "object" && detail && "step" in detail) {
          setError(
            `${detail.step} failed: ${detail.stderr?.slice(0, 500) ?? res.statusText}`,
          );
        } else {
          setError(
            typeof detail === "string"
              ? detail
              : JSON.stringify(data.detail ?? data),
          );
        }
        return;
      }

      // setDashboardRevision((r) => r + 1);
      setMessage(
        typeof data.message === "string"
          ? data.message
          : "Pipeline ran successfully.",
      );
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") {
        setError("Request timed out (pipeline can take a long time).");
      } else {
        setError(e instanceof Error ? e.message : "Request failed.");
      }
    } finally {
      window.clearTimeout(timeoutId);
      setLoading(false);
    }
  }

  return (
    <div className="page page--dashboard">
      <header className="home-header">
        <h1 className="home-title">Hello, {user.displayName}</h1>
        <p className="home-sub">
          Last.fm: <strong>{user.lastfmUsername}</strong>
        </p>
      </header>

      <div className="card card--intro">
        <h2 className="home-h2">What you&apos;ll see</h2>
        <ul className="home-list">
          <li>How habits shift across weeks, months, seasons, and years</li>
          <li>Exploration vs. focus in your artist and genre diversity</li>
          <li>ML clusters that summarize different listening modes over time</li>
        </ul>
      </div>

      <div className="home-actions">
        <button type="button" onClick={handleFetchData} disabled={loading}>
          {loading ? "Running pipeline…" : "Fetch my data"}
        </button>
        <button type="button" className="btn-secondary" onClick={onLogout}>
          Log out
        </button>
      </div>
      {message ? (
        <p className="home-status" role="status">
          {message}
        </p>
      ) : null}
      {error ? (
        <p className="home-error" role="alert">
          {error}
        </p>
      ) : null}

      {/* Graphs & insight cards — re-enable when ready: */}
      {/* <Dashboard username={user.lastfmUsername} revision={dashboardRevision} /> */}
    </div>
  );
}
