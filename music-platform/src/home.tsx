import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Dashboard } from "./Dashboard";
import {
  getPipelineSuccessAt,
  hasFetchedLastfmUsernameBefore,
  recordLastfmUsernameFetched,
  recordPipelineSuccessAt,
  pipelineSuccessIsFresh,
} from "./lastfmFetchMeta";

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
  const navigate = useNavigate();
  const location = useLocation();
  const autoFetchStarted = useRef(false);

  const [loading, setLoading] = useState(false);
  const [silentRefreshing, setSilentRefreshing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dashboardRevision, setDashboardRevision] = useState(0);
  const [hasDashboardData, setHasDashboardData] = useState<boolean | null>(null);

  const handleFetchData = useCallback(
    async (opts?: { silent?: boolean }) => {
      const silent = opts?.silent ?? false;
      if (silent) {
        setSilentRefreshing(true);
      } else {
        setLoading(true);
      }
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
              `${detail.step} failed: ${
                detail.stderr?.slice(0, 500) ?? res.statusText
              }`,
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

        recordLastfmUsernameFetched(user.lastfmUsername);
        recordPipelineSuccessAt(user.lastfmUsername);
        setHasDashboardData(true);
        setDashboardRevision((r) => r + 1);
        if (!silent) {
          setMessage(
            typeof data.message === "string"
              ? data.message
              : "Pipeline ran successfully.",
          );
        }
      } catch (e) {
        if (e instanceof Error && e.name === "AbortError") {
          setError("Request timed out (pipeline can take a long time).");
        } else {
          setError(e instanceof Error ? e.message : "Request failed.");
        }
      } finally {
        window.clearTimeout(timeoutId);
        if (silent) {
          setSilentRefreshing(false);
        } else {
          setLoading(false);
        }
      }
    },
    [user.lastfmUsername],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `/api/dashboard/${encodeURIComponent(user.lastfmUsername)}`,
        );
        const json = await res.json().catch(() => ({}));
        if (!cancelled && res.ok) {
          const has = !!json.hasData;
          setHasDashboardData(has);
          if (
            has &&
            !hasFetchedLastfmUsernameBefore(user.lastfmUsername)
          ) {
            recordLastfmUsernameFetched(user.lastfmUsername);
          }
        } else if (!cancelled) {
          setHasDashboardData(false);
        }
      } catch {
        if (!cancelled) setHasDashboardData(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user.lastfmUsername]);

  useEffect(() => {
    const st = location.state as { pipelineAutoStart?: boolean } | null;
    if (!st?.pipelineAutoStart || autoFetchStarted.current) return;
    autoFetchStarted.current = true;
    navigate(".", { replace: true, state: {} });
    void handleFetchData({ silent: true });
  }, [location.state, navigate, handleFetchData]);

  const showFetchButton = hasDashboardData !== true;

  const FRESH_MS = 45 * 60 * 1000;

  const handleGetRecentData = useCallback(() => {
    if (pipelineSuccessIsFresh(user.lastfmUsername, FRESH_MS)) {
      const at = getPipelineSuccessAt(user.lastfmUsername);
      const ago = at
        ? `Last refresh: ${at.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })}.`
        : "";
      setMessage(
        `${ago} Your data is already up to date. Try again in a bit for another full refresh.`,
      );
      return;
    }
    void handleFetchData();
  }, [user.lastfmUsername, handleFetchData]);

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
          <li>Listening personality traits from your stats (simple cards)</li>
          <li>Volume, variety, and discovery trends over time</li>
          <li>Seasonal and weekend patterns, plus your top artists, albums, and tracks</li>
        </ul>
      </div>

      {silentRefreshing ? (
        <p className="home-pipeline-quiet" role="status">
          Refreshing your Last.fm data in the background…
        </p>
      ) : null}

      <div className="home-actions">
        {showFetchButton ? (
          <button type="button" onClick={() => void handleFetchData()} disabled={loading}>
            {loading ? "Running pipeline…" : "Fetch my data"}
          </button>
        ) : null}
        {hasDashboardData ? (
          <button
            type="button"
            className="btn-secondary"
            onClick={() => void handleGetRecentData()}
            disabled={loading}
          >
            {loading ? "Updating…" : "Get recent data"}
          </button>
        ) : null}
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

      <Dashboard username={user.lastfmUsername} revision={dashboardRevision} />
    </div>
  );
}
