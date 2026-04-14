import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type PersonalityCard = {
  headline: string;
  detail: string;
  kind: string;
};

export type TrendsMonthlyRow = {
  month: string;
  total_listens: number;
  artist_entropy: number;
  new_artists: number;
  discovery_rate: number;
};

export type TopArtistRow = {
  name: string;
  plays: number;
  imageUrl: string | null;
};

export type TopAlbumRow = {
  artist: string;
  album: string;
  plays: number;
  coverUrl: string | null;
};

export type TopTrackRow = {
  artist: string;
  track: string;
  plays: number;
  coverUrl: string | null;
};

export type TopStuffWindow = {
  topArtists: TopArtistRow[];
  topAlbums: TopAlbumRow[];
  topTracks: TopTrackRow[];
  windowLabel: string;
};

export type WeekendListening = {
  weekendPercent: number;
  weekdayPercent: number;
  detail: string;
};

export type DashboardPayload = {
  username: string;
  hasData: boolean;
  dateRange: { start: string; end: string } | null;
  seasonalProfile: Record<string, unknown>[];
  personalityCards?: PersonalityCard[];
  trendsMonthly?: TrendsMonthlyRow[];
  weekendListening?: WeekendListening | null;
  topStuff?: {
    week: TopStuffWindow;
    month: TopStuffWindow;
    year: TopStuffWindow;
  };
};

const ACCENT = "#6366f1";
const MUTED = "#94a3b8";
const GRID = "#334155";

const tooltipProps = {
  contentStyle: {
    background: "#0f172a",
    border: `1px solid ${GRID}`,
    borderRadius: 8,
    color: "#e5e7eb",
  },
};

const SEASON_ORDER = ["winter", "spring", "summer", "fall"];

type MainTabId = "personality" | "trends" | "patterns" | "tops";
type TopRangeId = "week" | "month" | "year";

const MAIN_TABS: { id: MainTabId; label: string }[] = [
  { id: "personality", label: "Listening personality" },
  { id: "trends", label: "Trends over time" },
  { id: "patterns", label: "Patterns" },
  { id: "tops", label: "My  stuff" },
];

const TOP_RANGE_TABS: { id: TopRangeId; label: string }[] = [
  { id: "week", label: "Last 7 days" },
  { id: "month", label: "Last 30 days" },
  { id: "year", label: "Last 365 days" },
];

function ChartBlock({
  headline,
  subtitle,
  children,
}: {
  headline: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <div className="chart-block">
      <h3 className="chart-headline">{headline}</h3>
      <div className="chart-block__viz">{children}</div>
      <p className="chart-subtitle">{subtitle}</p>
    </div>
  );
}

function MediaThumb({
  url,
  fallbackLetter,
  className,
}: {
  url: string | null;
  fallbackLetter: string;
  className: string;
}) {
  const [failed, setFailed] = useState(false);
  const letter = fallbackLetter.trim().slice(0, 1).toUpperCase() || "?";

  if (url && !failed) {
    return (
      <img
        className={className}
        src={url}
        alt=""
        loading="lazy"
        onError={() => setFailed(true)}
      />
    );
  }

  return (
    <span className={`${className} top-thumb-fallback`} aria-hidden>
      {letter}
    </span>
  );
}

export function Dashboard({
  username,
  revision = 0,
}: {
  username: string;
  revision?: number;
}) {
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mainTab, setMainTab] = useState<MainTabId>("personality");
  const [topRange, setTopRange] = useState<TopRangeId>("week");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/dashboard/${encodeURIComponent(username)}`);
      const json = await res.json();
      if (!res.ok) {
        setError(
          typeof json.detail === "string" ? json.detail : "Failed to load dashboard",
        );
        setData(null);
        return;
      }
      setData(json as DashboardPayload);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [username]);

  useEffect(() => {
    void load();
  }, [load, revision]);

  if (loading && !data) {
    return (
      <div className="dashboard-loading" aria-busy="true">
        Loading your analytics…
      </div>
    );
  }

  if (error) {
    return (
      <p className="dashboard-error" role="alert">
        {error}
      </p>
    );
  }

  if (!data) return null;

  const personality = data.personalityCards ?? [];
  const trendsRaw = data.trendsMonthly ?? [];
  const trendsChart = trendsRaw.map((row) => ({
    monthLabel: String(row.month),
    listens: Number(row.total_listens) || 0,
    variety: Number(row.artist_entropy) || 0,
    discovery: Number(row.new_artists) || 0,
  }));

  const seasonalProfileSorted = [...data.seasonalProfile].sort(
    (a, b) =>
      SEASON_ORDER.indexOf(String(a.season).toLowerCase()) -
      SEASON_ORDER.indexOf(String(b.season).toLowerCase()),
  );
  const seasonalBars = seasonalProfileSorted.map((row) => ({
    season: String(row.season).slice(0, 3).toUpperCase(),
    fullSeason: String(row.season),
    listens: Number(row.total_listens) || 0,
  }));

  const weekend = data.weekendListening;
  const weekendBars =
    weekend != null
      ? [
          {
            label: "Typical week (recent)",
            weekend: weekend.weekendPercent,
            weekday: weekend.weekdayPercent,
          },
        ]
      : [];

  const topStuff = data.topStuff;
  const topWindow = topStuff?.[topRange];

  return (
    <div className="dashboard-root">
      <div className="dashboard-meta">
        {data.dateRange ? (
          <p className="dashboard-range">
            Data window: {data.dateRange.start} → {data.dateRange.end}
          </p>
        ) : null}
      </div>

      {!data.hasData ? (
        <p className="dashboard-empty">
          No processed history yet. Fetch your data to unlock these tabs.
        </p>
      ) : null}

      {data.hasData ? (
        <>
          <nav className="dashboard-main-tabs" aria-label="Dashboard sections">
            {MAIN_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={mainTab === t.id ? "dash-tab dash-tab--active" : "dash-tab"}
                onClick={() => setMainTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>

          <div className="dashboard-tab-panel">
            {mainTab === "personality" ? (
              <section className="dashboard-section" aria-labelledby="personality-heading">
                <h2 id="personality-heading" className="dashboard-section-title">
                  Your listening personality
                </h2>
                {personality.length > 0 ? (
                  <div className="personality-grid">
                    {personality.map((card, i) => (
                      <article
                        key={`${card.headline}-${i}`}
                        className={`personality-card personality-card--${card.kind}`}
                      >
                        <h3 className="personality-card__headline">{card.headline}</h3>
                        <p className="personality-card__detail">{card.detail}</p>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="dashboard-muted">
                    Run a full pipeline fetch to unlock personality cards from your monthly
                    patterns.
                  </p>
                )}
              </section>
            ) : null}

            {mainTab === "trends" ? (
              <section className="dashboard-section" aria-labelledby="trends-heading">
                <h2 id="trends-heading" className="dashboard-section-title">
                  Your trends over time
                </h2>
                <div className="trends-grid trends-grid--tabbed">
                  <ChartBlock
                    headline="How much you listened"
                    subtitle="Total plays per month. Higher spikes usually mean more time with music that month."
                  >
                    <ResponsiveContainer width="100%" height={260}>
                      <LineChart data={trendsChart} margin={{ left: 8, right: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                        <XAxis dataKey="monthLabel" tick={{ fill: MUTED, fontSize: 11 }} />
                        <YAxis tick={{ fill: MUTED, fontSize: 11 }} />
                        <Tooltip
                          {...tooltipProps}
                          formatter={(value: number) => [`${value}`, "Listening volume"]}
                        />
                        <Line
                          type="monotone"
                          dataKey="listens"
                          stroke={ACCENT}
                          dot={false}
                          name="Listening volume"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </ChartBlock>

                  <ChartBlock
                    headline="Your music variety over time"
                    subtitle="Variety scores how spread out your plays are across artists. Higher means a wider mix in the same number of listens."
                  >
                    <ResponsiveContainer width="100%" height={260}>
                      <LineChart data={trendsChart} margin={{ left: 8, right: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                        <XAxis dataKey="monthLabel" tick={{ fill: MUTED, fontSize: 11 }} />
                        <YAxis tick={{ fill: MUTED, fontSize: 11 }} />
                        <Tooltip
                          {...tooltipProps}
                          formatter={(value: number) => [`${value.toFixed(2)}`, "Variety"]}
                        />
                        <Line
                          type="monotone"
                          dataKey="variety"
                          stroke="#22d3ee"
                          dot={false}
                          name="Variety"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </ChartBlock>

                  <ChartBlock
                    headline="Discovery each month"
                    subtitle="Artists who appear in a week but not the week before, summed by month — a simple “new faces” signal, not first-time-ever in your library."
                  >
                    <ResponsiveContainer width="100%" height={260}>
                      <LineChart data={trendsChart} margin={{ left: 8, right: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                        <XAxis dataKey="monthLabel" tick={{ fill: MUTED, fontSize: 11 }} />
                        <YAxis tick={{ fill: MUTED, fontSize: 11 }} />
                        <Tooltip
                          {...tooltipProps}
                          formatter={(value: number) => [`${value}`, "Discovery (count)"]}
                        />
                        <Line
                          type="monotone"
                          dataKey="discovery"
                          stroke="#f472b6"
                          dot={false}
                          name="Discovery"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </ChartBlock>
                </div>
              </section>
            ) : null}

            {mainTab === "patterns" ? (
              <section className="dashboard-section" aria-labelledby="patterns-heading">
                <h2 id="patterns-heading" className="dashboard-section-title">
                  Your patterns
                </h2>
                <div className="patterns-grid patterns-grid--tabbed">
                  {seasonalBars.length > 0 ? (
                    <ChartBlock
                      headline="Seasonal listening"
                      subtitle="Total plays across all years, grouped by season — good for spotting long-run habits."
                    >
                      <ResponsiveContainer width="100%" height={260}>
                        <BarChart data={seasonalBars} margin={{ left: 8, right: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                          <XAxis dataKey="season" tick={{ fill: MUTED }} />
                          <YAxis tick={{ fill: MUTED, fontSize: 11 }} />
                          <Tooltip
                            {...tooltipProps}
                            formatter={(value: number) => [`${value} plays`, "Listening volume"]}
                          />
                          <Bar
                            dataKey="listens"
                            fill={ACCENT}
                            name="Listening volume"
                            radius={[6, 6, 0, 0]}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </ChartBlock>
                  ) : null}

                  {weekendBars.length > 0 ? (
                    <ChartBlock
                      headline="Weekend vs weekday listening"
                      subtitle={weekend?.detail ?? ""}
                    >
                      <ResponsiveContainer width="100%" height={200}>
                        <BarChart
                          data={weekendBars}
                          layout="vertical"
                          margin={{ left: 8, right: 8, top: 8 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                          <XAxis
                            type="number"
                            domain={[0, 100]}
                            tick={{ fill: MUTED, fontSize: 11 }}
                          />
                          <YAxis
                            type="category"
                            dataKey="label"
                            width={160}
                            tick={{ fill: MUTED, fontSize: 11 }}
                          />
                          <Tooltip
                            {...tooltipProps}
                            formatter={(value: number, name: string) => [
                              `${value}%`,
                              name === "weekend" ? "Weekend listening" : "Weekday listening",
                            ]}
                          />
                          <Bar
                            dataKey="weekend"
                            stackId="split"
                            fill="#818cf8"
                            name="weekend"
                            radius={[0, 0, 0, 0]}
                          />
                          <Bar
                            dataKey="weekday"
                            stackId="split"
                            fill="#38bdf8"
                            name="weekday"
                            radius={[0, 6, 6, 0]}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </ChartBlock>
                  ) : null}
                </div>
              </section>
            ) : null}

            {mainTab === "tops" ? (
              <section className="dashboard-section" aria-labelledby="tops-heading">
                <h2 id="tops-heading" className="dashboard-section-title">
                  Your Favorites
                </h2>
                {/* <p className="tops-spotify-note">
                  Art, album, and track images come from the Spotify API when{" "}
                  <code className="inline-code">SPOTIFY_CLIENT_ID</code> and{" "}
                  <code className="inline-code">SPOTIFY_CLIENT_SECRET</code> are set on the
                  server.
                </p> */}

                <nav className="dashboard-subtabs" aria-label="Time range for top lists">
                  {TOP_RANGE_TABS.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      className={
                        topRange === t.id ? "dash-tab dash-tab--sm dash-tab--active" : "dash-tab dash-tab--sm"
                      }
                      onClick={() => setTopRange(t.id)}
                    >
                      {t.label}
                    </button>
                  ))}
                </nav>

                {topWindow ? (
                  <>
                    <p className="tops-window-label">{topWindow.windowLabel}</p>
                    {topWindow.topArtists.length === 0 &&
                    topWindow.topAlbums.length === 0 &&
                    topWindow.topTracks.length === 0 ? (
                      <p className="dashboard-muted">
                        No plays in this window. Try a longer range, or run{" "}
                        <strong>Fetch my data</strong> so{" "}
                        <code className="inline-code">{username}_listening_history.csv</code>{" "}
                        is up to date.
                      </p>
                    ) : (
                      <div className="tops-grid" key={topRange}>
                        <div className="tops-column">
                          <h3 className="tops-column__title">Top artists</h3>
                          <ul className="tops-list">
                            {topWindow.topArtists.map((a) => (
                              <li key={a.name} className="tops-row">
                                <MediaThumb
                                  url={a.imageUrl}
                                  fallbackLetter={a.name}
                                  className="top-avatar-img"
                                />
                                <div className="tops-row__text">
                                  <span className="tops-row__name">{a.name}</span>
                                  <span className="tops-row__meta">{a.plays} plays</span>
                                </div>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="tops-column">
                          <h3 className="tops-column__title">Top albums</h3>
                          <ul className="tops-list">
                            {topWindow.topAlbums.map((row) => (
                              <li
                                key={`${row.artist} — ${row.album}`}
                                className="tops-row tops-row--stack"
                              >
                                <MediaThumb
                                  url={row.coverUrl}
                                  fallbackLetter={row.album}
                                  className="top-cover-img"
                                />
                                <div className="tops-row__text">
                                  <span className="tops-row__name">{row.album}</span>
                                  <span className="tops-row__meta">
                                    {row.artist} · {row.plays} plays
                                  </span>
                                </div>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="tops-column">
                          <h3 className="tops-column__title">Top tracks</h3>
                          <ul className="tops-list">
                            {topWindow.topTracks.map((row) => (
                              <li
                                key={`${row.artist} — ${row.track}`}
                                className="tops-row tops-row--stack"
                              >
                                <MediaThumb
                                  url={row.coverUrl}
                                  fallbackLetter={row.track}
                                  className="top-cover-img"
                                />
                                <div className="tops-row__text">
                                  <span className="tops-row__name">{row.track}</span>
                                  <span className="tops-row__meta">
                                    {row.artist} · {row.plays} plays
                                  </span>
                                </div>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="dashboard-muted">
                    Top lists are unavailable. Ensure your listening history export exists.
                  </p>
                )}
              </section>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}
