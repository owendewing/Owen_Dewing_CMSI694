import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type ChartCaptionKey =
  | "volume"
  | "variety"
  | "genres"
  | "newArtist"
  | "listenHour"
  | "seasonal"
  | "weekend";

export type PersonalityCard = {
  headline: string;
  detail: string;
  kind: string;
};

export type ListeningPersonalityInsight = {
  title: string;
  body: string;
};

export type ListeningPersonalityPayload = {
  source: "anthropic" | "fallback";
  tagline: string;
  insights: ListeningPersonalityInsight[];
  chartCaptions: Partial<Record<ChartCaptionKey, string>>;
  /** Present when ANTHROPIC_API_KEY was set but the API call or JSON parse failed. */
  anthropicError?: string;
};

export type TrendsMonthlyRow = {
  month: string;
  total_listens: number;
  artist_entropy: number;
  new_artists: number;
  discovery_rate: number;
};

export type VolumeBarRow = { label: string; plays: number };

export type ListeningVolumeBlock = {
  rangeLabel: string;
  bars: VolumeBarRow[];
};

export type ListeningVolumeByRange = {
  lastWeek: ListeningVolumeBlock;
  lastMonth: ListeningVolumeBlock;
  lastYear: ListeningVolumeBlock;
  allTime: ListeningVolumeBlock;
};

export type YearlyListenRow = {
  year: number;
  total_listens: number;
  avg_listen_hour: number | null;
  unique_genres: number | null;
  genre_entropy: number | null;
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
  /** Raw weekly feature rows from the pipeline (snake_case keys). */
  weekly?: Record<string, unknown>[];
  listeningPersonality?: ListeningPersonalityPayload;
  personalityCards?: PersonalityCard[];
  trendsMonthly?: TrendsMonthlyRow[];
  yearly?: Record<string, unknown>[];
  /** Day / month / year buckets from listening history for the volume chart. */
  listeningVolumeByRange?: ListeningVolumeByRange;
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

const SEASON_DISPLAY: Record<string, { name: string; fill: string }> = {
  winter: { name: "Winter", fill: "#38bdf8" },
  spring: { name: "Spring", fill: "#4ade80" },
  summer: { name: "Summer", fill: "#fbbf24" },
  fall: { name: "Fall", fill: "#fb923c" },
};

type MainTabId = "tops" | "personality" | "trends" | "patterns";
type TopRangeId = "week" | "month" | "year";
type VolumeRangeId = "lastWeek" | "lastMonth" | "lastYear" | "allTime";

const VOLUME_RANGE_TABS: { id: VolumeRangeId; label: string }[] = [
  { id: "lastWeek", label: "Last 7 days" },
  { id: "lastMonth", label: "Last 30 days" },
  { id: "lastYear", label: "Last 12 months" },
  { id: "allTime", label: "All years" },
];

const MAIN_TABS: { id: MainTabId; label: string }[] = [
  { id: "tops", label: "My stuff" },
  { id: "personality", label: "Listening personality" },
  { id: "trends", label: "Trends over time" },
  { id: "patterns", label: "Patterns" },
];

const TOP_RANGE_TABS: { id: TopRangeId; label: string }[] = [
  { id: "week", label: "Last 7 days" },
  { id: "month", label: "Last 30 days" },
  { id: "year", label: "Last 365 days" },
];

function numOrNull(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function meanWeeklyColumn(weekly: Record<string, unknown>[], col: string): number | null {
  const nums = weekly
    .map((r) => numOrNull(r[col]))
    .filter((x): x is number => x != null);
  if (nums.length === 0) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function quantile(sorted: number[], q: number): number | null {
  if (sorted.length === 0) return null;
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  const a = sorted[base];
  const b = sorted[Math.min(sorted.length - 1, base + 1)];
  return a + (b - a) * rest;
}

type VarietyZone = "Loyalist" | "Balanced" | "Explorer";

function varietyZone(score: number, tLow: number, tHigh: number): VarietyZone {
  if (score < tLow) return "Loyalist";
  if (score < tHigh) return "Balanced";
  return "Explorer";
}

function zoneColor(z: VarietyZone): string {
  if (z === "Explorer") return "#22c55e";
  if (z === "Balanced") return "#38bdf8";
  return "#f59e0b";
}

/** e.g. 14.25 -> "2:15 PM" */
function formatClockHour(decimalHour: number): string {
  const total = Math.round(decimalHour * 60);
  const h24 = Math.floor(total / 60) % 24;
  const m = total % 60;
  const period = h24 >= 12 ? "PM" : "AM";
  const hh = h24 % 12 || 12;
  return `${hh}:${m.toString().padStart(2, "0")} ${period}`;
}

function ListeningHourDial({
  avgHour,
}: {
  avgHour: number;
}) {
  // The hand starts pointing at 12, and SVG positive rotation is clockwise (y axis down),
  // so 1:00 should rotate +30 degrees, 3:00 -> +90, etc.
  const angle = (avgHour % 12) * 30;
  const shown = formatClockHour(avgHour);

  return (
    <div className="listen-hour-dial-layout">
      <svg
        className="listen-hour-dial"
        viewBox="0 0 220 220"
        role="img"
        aria-label={`Average listening time about ${shown}`}
      >
        <defs>
          <radialGradient id="dialFace" cx="35%" cy="30%" r="70%">
            <stop offset="0%" stopColor="#1f2937" />
            <stop offset="55%" stopColor="#0b1220" />
            <stop offset="100%" stopColor="#020617" />
          </radialGradient>
        </defs>
        <circle cx="110" cy="110" r="104" fill="url(#dialFace)" stroke="#334155" strokeWidth="2" />
        <circle cx="110" cy="110" r="78" fill="#020617" stroke="#0f172a" strokeWidth="1.5" />
        {Array.from({ length: 12 }, (_, i) => (
          <g key={i} transform={`rotate(${i * 30} 110 110)`}>
            <line
              x1="110"
              y1="14"
              x2="110"
              y2={i % 3 === 0 ? "30" : "24"}
              stroke="#94a3b8"
              strokeWidth={i % 3 === 0 ? 2.6 : 1.6}
              strokeLinecap="round"
              opacity={0.85}
            />
          </g>
        ))}
        {/* numerals (kept minimal to reduce clutter) */}
        <text x="110" y="52" textAnchor="middle" fill="#e2e8f0" fontSize="14" fontWeight="700">
          12
        </text>
        <text x="168" y="116" textAnchor="middle" fill="#e2e8f0" fontSize="14" fontWeight="700">
          3
        </text>
        <text x="110" y="178" textAnchor="middle" fill="#e2e8f0" fontSize="14" fontWeight="700">
          6
        </text>
        <text x="52" y="116" textAnchor="middle" fill="#e2e8f0" fontSize="14" fontWeight="700">
          9
        </text>
        {/* hand */}
        <g transform={`rotate(${angle} 110 110)`}>
          <line
            x1="110"
            y1="110"
            x2="110"
            y2="42"
            stroke="#60a5fa"
            strokeWidth="5"
            strokeLinecap="round"
          />
        </g>
        <circle cx="110" cy="110" r="7" fill="#1e293b" stroke="#64748b" strokeWidth="1.5" />
      </svg>
      <div className="listen-hour-caption">Peak Listening Time {shown}</div>
    </div>
  );
}

function NewArtistRateRing({ rate }: { rate: number }) {
  const r = 68;
  const c = 2 * Math.PI * r;
  const clamped = Math.min(1, Math.max(0, rate));
  const dash = clamped * c;
  const pct = (clamped * 100).toFixed(1);

  return (
    <div className="pattern-new-artist-ring">
      <svg
        viewBox="0 0 200 200"
        width={200}
        height={200}
        role="img"
        aria-label={`Average new artist rate ${pct} percent of plays per week`}
      >
        <circle cx="100" cy="100" r={r} fill="none" stroke="#1e293b" strokeWidth={14} />
        <circle
          cx="100"
          cy="100"
          r={r}
          fill="none"
          stroke="#a78bfa"
          strokeWidth={14}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
          transform="rotate(-90 100 100)"
        />
        <text
          x="100"
          y="100"
          textAnchor="middle"
          dominantBaseline="central"
          fill="#f1f5f9"
          fontSize="26"
          fontWeight="700"
        >
          {pct}%
        </text>
        <text
          x="100"
          y="128"
          textAnchor="middle"
          fill="#94a3b8"
          fontSize="11"
        >
          avg weekly rate
        </text>
      </svg>
    </div>
  );
}

function ChartBlock({
  headline,
  subtitle,
  beforeViz,
  children,
}: {
  headline: string;
  subtitle: string;
  /** e.g. time-range tabs shown above the chart area */
  beforeViz?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="chart-block">
      <h3 className="chart-headline">{headline}</h3>
      {beforeViz ? <div className="chart-block__before-viz">{beforeViz}</div> : null}
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
  const [mainTab, setMainTab] = useState<MainTabId>("tops");
  const [topRange, setTopRange] = useState<TopRangeId>("week");
  const [volumeRange, setVolumeRange] = useState<VolumeRangeId>("lastMonth");
  const [monthlyRange, setMonthlyRange] = useState<"last6" | "last12" | "all">("last12");

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

  const lp = data.listeningPersonality;
  const chartCap = lp?.chartCaptions ?? {};
  const claudePersonalityCards: PersonalityCard[] | null =
    lp?.source === "anthropic" &&
    Array.isArray(lp.insights) &&
    lp.insights.length >= 3
      ? lp.insights.map((ins, i) => ({
          headline: ins.title,
          detail: ins.body?.trim() ? ins.body : ins.title,
          kind: i % 2 === 0 ? "highlight" : "info",
        }))
      : null;
  const personality = claudePersonalityCards ?? (data.personalityCards ?? []);
  const trendsRaw = data.trendsMonthly ?? [];
  const trendsChart = trendsRaw.map((row) => ({
    monthLabel: String(row.month),
    listens: Number(row.total_listens) || 0,
    variety: Number(row.artist_entropy) || 0,
    discovery: Number(row.new_artists) || 0,
  }));

  const listeningVolume = data.listeningVolumeByRange;
  const volumeBlock = listeningVolume?.[volumeRange];
  const volumeBars = volumeBlock?.bars ?? [];
  const volumeRangeHint = volumeBlock?.rangeLabel ?? "";

  const volumeSubtitleByRange: Record<VolumeRangeId, string> = {
    lastWeek:
      "Each bar is one calendar day. A taller bar means more tracks logged that day — usually a heavier listening day.",
    lastMonth:
      "Each bar is one day over the last 30 days. Use this to spot streaks, quiet days, or weekends vs weekdays.",
    lastYear:
      "Each bar is one calendar month in your most recent year of history. Compare months to see seasons or busy periods.",
    allTime:
      "Each bar is a full calendar year. Great for seeing long-term growth or which years you leaned on music most.",
  };
  const volumeSubtitle =
    chartCap.volume?.trim() || volumeSubtitleByRange[volumeRange];

  const slicedMonthly =
    monthlyRange === "all"
      ? trendsChart
      : monthlyRange === "last6"
        ? trendsChart.slice(-6)
        : trendsChart.slice(-12);

  const varietyChart = slicedMonthly.map((r) => ({
    label: r.monthLabel,
    score: r.variety,
  }));

  const varietyScores = varietyChart
    .map((r) => r.score)
    .filter((x) => Number.isFinite(x))
    .sort((a, b) => a - b);
  const tLow = quantile(varietyScores, 1 / 3) ?? 0;
  const tHigh = quantile(varietyScores, 2 / 3) ?? tLow + 1;
  const currentVariety = varietyChart.length ? varietyChart[varietyChart.length - 1].score : null;
  const currentZone =
    currentVariety != null ? varietyZone(currentVariety, tLow, tHigh) : null;

  const varietyDomain = (() => {
    const vals = varietyScores;
    if (vals.length === 0) return ["auto", "auto"] as const;
    const min = vals[0];
    const max = vals[vals.length - 1];
    const span = Math.max(0.15, max - min);
    const pad = span * 0.15;
    return [min - pad, max + pad] as const;
  })();

  const volumeTickAngle =
    volumeRange === "lastMonth" ? -42 : volumeRange === "lastYear" ? -35 : 0;
  const volumeChartHeight =
    volumeRange === "lastMonth" ? 300 : volumeRange === "lastYear" ? 280 : 260;

  const seasonalProfileSorted = [...data.seasonalProfile].sort(
    (a, b) =>
      SEASON_ORDER.indexOf(String(a.season).toLowerCase()) -
      SEASON_ORDER.indexOf(String(b.season).toLowerCase()),
  );
  const seasonalPie = seasonalProfileSorted.map((row) => {
    const key = String(row.season).toLowerCase();
    const meta = SEASON_DISPLAY[key] ?? { name: String(row.season), fill: "#94a3b8" };
    return {
      name: meta.name,
      plays: Number(row.total_listens) || 0,
      fill: meta.fill,
    };
  });
  const seasonalPlaysTotal = seasonalPie.reduce((a, b) => a + b.plays, 0);

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

  const weeklyRows = data.weekly ?? [];

  const meanNewArtistRate = meanWeeklyColumn(weeklyRows, "new_artist_rate");

  const yearlyRaw = data.yearly ?? [];
  const yearlyRows: YearlyListenRow[] = yearlyRaw
    .map((r) => ({
      year: Number(r.year),
      total_listens: Number(r.total_listens) || 0,
      avg_listen_hour: numOrNull(r.avg_listen_hour),
      unique_genres: numOrNull(r.unique_genres),
      genre_entropy: numOrNull(r.genre_entropy),
    }))
    .filter((r) => Number.isFinite(r.year));

  const avgListenHourWeighted = (() => {
    const rows = yearlyRows.filter((r) => r.avg_listen_hour != null && r.total_listens > 0);
    if (rows.length === 0) return null;
    const w = rows.reduce((a, b) => a + b.total_listens, 0);
    if (w <= 0) return null;
    const s = rows.reduce((a, b) => a + b.total_listens * (b.avg_listen_hour ?? 0), 0);
    return s / w;
  })();

  const yearlyUniqueGenresChart = yearlyRows
    .filter((r) => r.unique_genres != null)
    .map((r) => ({ yearLabel: String(r.year), count: r.unique_genres as number }));

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
                  {claudePersonalityCards
                    ? "Your AI-generated listening personality"
                    : "Your listening personality"}
                </h2>
                {!claudePersonalityCards ? (
                  <p className="dashboard-muted personality-blurb">
                    Rule-based traits from your feature files.
                    {lp?.anthropicError ? (
                      <>
                        {" "}
                        <span className="personality-api-hint" title={lp.anthropicError}>
                          Claude could not run ({lp.anthropicError.slice(0, 80)}
                          {lp.anthropicError.length > 80 ? "…" : ""}).
                        </span>
                      </>
                    ) : null}
                  </p>
                ) : null}
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
                    Run <strong>Fetch my data</strong> so monthly feature files exist — traits are derived from those
                    stats.
                  </p>
                )}
              </section>
            ) : null}

            {mainTab === "trends" ? (
              <section className="dashboard-section" aria-labelledby="trends-heading">
                <h2 id="trends-heading" className="dashboard-section-title">
                  Your trends over time
                </h2>
                {/* <p className="trends-intro">
                  Three views of your Last.fm-style history: how often you hit play, how wide your artist mix was
                  each month, and how many “new that week” artists showed up. Numbers come from your export — not a
                  live stream.
                </p> */}
                <div className="trends-grid trends-grid--tabbed">
                  <div className="trends-volume-wrap">
                    <ChartBlock
                      headline="How much you listened"
                      subtitle={volumeSubtitle}
                      beforeViz={
                        <>
                          <nav className="trends-volume-tabs" aria-label="Time range for plays">
                            {VOLUME_RANGE_TABS.map((t) => (
                              <button
                                key={t.id}
                                type="button"
                                className={
                                  volumeRange === t.id
                                    ? "dash-tab dash-tab--sm dash-tab--active"
                                    : "dash-tab dash-tab--sm"
                                }
                                onClick={() => setVolumeRange(t.id)}
                              >
                                {t.label}
                              </button>
                            ))}
                          </nav>
                          {volumeRangeHint ? (
                            <p className="trends-range-hint">{volumeRangeHint}</p>
                          ) : null}
                        </>
                      }
                    >
                      {volumeBars.length > 0 ? (
                        <ResponsiveContainer width="100%" height={volumeChartHeight}>
                          <BarChart
                            data={volumeBars}
                            margin={{
                              left: 4,
                              right: 8,
                              top: 4,
                              bottom: volumeTickAngle !== 0 ? 52 : 12,
                            }}
                          >
                            <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
                            <XAxis
                              dataKey="label"
                              tick={{ fill: MUTED, fontSize: 10 }}
                              interval={0}
                              angle={volumeTickAngle}
                              textAnchor="end"
                              height={volumeTickAngle !== 0 ? 48 : 28}
                            />
                            <YAxis
                              tick={{ fill: MUTED, fontSize: 11 }}
                              allowDecimals={false}
                              label={{
                                value: "Plays",
                                angle: -90,
                                position: "insideLeft",
                                fill: MUTED,
                                fontSize: 11,
                                offset: 4,
                              }}
                            />
                            <Tooltip
                              {...tooltipProps}
                              formatter={(value: number) => [
                                `${value.toLocaleString()} plays`,
                              ]}
                              labelFormatter={(label) => String(label)}
                            />
                            <Bar
                              dataKey="plays"
                              fill={ACCENT}
                              name="Plays"
                              radius={[5, 5, 0, 0]}
                              maxBarSize={volumeRange === "lastMonth" ? 14 : 48}
                            />
                          </BarChart>
                        </ResponsiveContainer>
                      ) : (
                        <p className="dashboard-muted trends-chart-fallback">
                          No day-level volume yet. Run <strong>Fetch my data</strong> so{" "}
                          <code className="inline-code">{username}_listening_history.csv</code> exists next to your
                          feature files.
                        </p>
                      )}
                    </ChartBlock>
                  </div>

                  <ChartBlock
                    headline="Artist variety"
                    subtitle={
                      chartCap.variety?.trim() ||
                      "Each month reflects how spread out your plays were across different artists in your monthly export—not genres. Dots: Loyalist (repeat favorites), Balanced, Explorer (wider artist mix)."
                    }
                    beforeViz={
                      <div className="trends-variety-controls">
                        <nav className="trends-volume-tabs" aria-label="Time range for monthly charts">
                          <button
                            type="button"
                            className={
                              monthlyRange === "last6"
                                ? "dash-tab dash-tab--sm dash-tab--active"
                                : "dash-tab dash-tab--sm"
                            }
                            onClick={() => setMonthlyRange("last6")}
                          >
                            Last 6 months
                          </button>
                          <button
                            type="button"
                            className={
                              monthlyRange === "last12"
                                ? "dash-tab dash-tab--sm dash-tab--active"
                                : "dash-tab dash-tab--sm"
                            }
                            onClick={() => setMonthlyRange("last12")}
                          >
                            Last 12 months
                          </button>
                          <button
                            type="button"
                            className={
                              monthlyRange === "all"
                                ? "dash-tab dash-tab--sm dash-tab--active"
                                : "dash-tab dash-tab--sm"
                            }
                            onClick={() => setMonthlyRange("all")}
                          >
                            All years
                          </button>
                        </nav>
                        {currentZone ? (
                          <div className="trends-zone-badge" style={{ borderColor: zoneColor(currentZone) }}>
                            <span className="trends-zone-dot" style={{ background: zoneColor(currentZone) }} />
                            Current: <strong>{currentZone}</strong>
                          </div>
                        ) : null}
                      </div>
                    }
                  >
                    {varietyChart.length > 0 ? (
                      <ResponsiveContainer width="100%" height={260}>
                        <LineChart data={varietyChart} margin={{ left: 8, right: 8, bottom: 28 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
                          <XAxis
                            dataKey="label"
                            tick={{ fill: MUTED, fontSize: 10 }}
                            interval="preserveStartEnd"
                            angle={-30}
                            textAnchor="end"
                            height={44}
                          />
                          <YAxis
                            tick={{ fill: MUTED, fontSize: 11 }}
                            domain={varietyDomain as any}
                            tickFormatter={(v: number) => Number(v).toFixed(1)}
                          />
                          <ReferenceLine y={tLow} stroke="#f59e0b" strokeDasharray="4 4" />
                          <ReferenceLine y={tHigh} stroke="#22c55e" strokeDasharray="4 4" />
                          <Tooltip
                            {...tooltipProps}
                            formatter={(value: number) => [
                              value.toFixed(2),
                              "Variety (higher = wider artist mix)",
                            ]}
                            labelFormatter={(l) => `Month: ${l}`}
                          />
                          <Line
                            type="monotone"
                            dataKey="score"
                            stroke="#e2e8f0"
                            strokeWidth={2}
                            dot={(props: any) => {
                              const score = Number(props?.payload?.score);
                              const z = Number.isFinite(score) ? varietyZone(score, tLow, tHigh) : "Balanced";
                              return (
                                <circle
                                  cx={props.cx}
                                  cy={props.cy}
                                  r={3.75}
                                  fill={zoneColor(z)}
                                  stroke="#0f172a"
                                  strokeWidth={1}
                                />
                              );
                            }}
                            activeDot={{ r: 5 }}
                            name="Variety"
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <p className="dashboard-muted">No monthly stats yet.</p>
                    )}
                  </ChartBlock>

                  {yearlyUniqueGenresChart.length > 0 ? (
                    <ChartBlock
                      headline="How Many Genres You Explored"
                      subtitle={
                        chartCap.genres?.trim() ||
                        "A simple count of distinct genres seen in your listens per year."
                      }
                    >
                      <div className="chart-viz-center">
                        <ResponsiveContainer width="100%" height={260}>
                          <BarChart data={yearlyUniqueGenresChart} margin={{ left: 4, right: 8, bottom: 12 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
                            <XAxis dataKey="yearLabel" tick={{ fill: MUTED, fontSize: 11 }} />
                            <YAxis tick={{ fill: MUTED, fontSize: 11 }} allowDecimals={false} />
                            <Tooltip
                              {...tooltipProps}
                              formatter={(value: number) => [`${value.toLocaleString()} genres`, "Unique genres"]}
                              labelFormatter={(l) => `Year: ${l}`}
                            />
                            <Bar dataKey="count" fill="#f59e0b" radius={[5, 5, 0, 0]} maxBarSize={52} />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </ChartBlock>
                  ) : null}
                </div>
              </section>
            ) : null}

            {mainTab === "patterns" ? (
              <section className="dashboard-section" aria-labelledby="patterns-heading">
                <h2 id="patterns-heading" className="dashboard-section-title">
                  Your patterns
                </h2>
                <div className="patterns-grid patterns-grid--tabbed">
                  {meanNewArtistRate != null ? (
                    <ChartBlock
                      headline="New artist rate"
                      subtitle={
                        chartCap.newArtist?.trim() ||
                        "How much of your listening comes from new artist discoveries each week."
                      }
                    >
                      <NewArtistRateRing rate={meanNewArtistRate} />
                    </ChartBlock>
                  ) : null}

                  <ChartBlock
                    headline="When You Listen Most"
                    subtitle={
                      chartCap.listenHour?.trim() ||
                      "Your most active time of day for music listening."
                    }
                  >
                    {avgListenHourWeighted != null ? (
                      <ListeningHourDial avgHour={avgListenHourWeighted} />
                    ) : (
                      <p className="dashboard-muted listening-radial-fallback">
                        No yearly average listening hour available yet.
                      </p>
                    )}
                  </ChartBlock>

                  {seasonalPie.length > 0 ? (
                    <ChartBlock
                      headline="Seasonal listening"
                      subtitle={
                        chartCap.seasonal?.trim() ||
                        "Share of all your listens by season (winter = Dec–Feb, spring = Mar–May, summer = Jun–Aug, fall = Sep–Nov)."
                      }
                    >
                      <ResponsiveContainer width="100%" height={280}>
                        <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                          <Pie
                            data={seasonalPie}
                            dataKey="plays"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            innerRadius="48%"
                            outerRadius="78%"
                            paddingAngle={2}
                            stroke="#0f172a"
                            strokeWidth={1}
                            label={({ name, percent }) =>
                              `${name} (${((percent ?? 0) * 100).toFixed(0)}%)`
                            }
                            labelLine={{ stroke: MUTED, strokeWidth: 1 }}
                          >
                            {seasonalPie.map((entry, i) => (
                              <Cell key={`${entry.name}-${i}`} fill={entry.fill} />
                            ))}
                          </Pie>
                          <Tooltip
                            {...tooltipProps}
                            content={({ active, payload }) => {
                              if (!active || !payload?.length) return null;
                              const row = payload[0].payload as {
                                name: string;
                                plays: number;
                              };
                              const pct =
                                seasonalPlaysTotal > 0
                                  ? ((row.plays / seasonalPlaysTotal) * 100).toFixed(1)
                                  : "0";
                              return (
                                <div style={{ ...tooltipProps.contentStyle, minWidth: 160 }}>
                                  <div style={{ fontWeight: 700, marginBottom: 6 }}>{row.name}</div>
                                  <div style={{ fontSize: 13 }}>
                                    {row.plays.toLocaleString()} plays
                                  </div>
                                  <div style={{ fontSize: 13, color: "#94a3b8", marginTop: 4 }}>
                                    {pct}% of total listening
                                  </div>
                                </div>
                              );
                            }}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    </ChartBlock>
                  ) : null}

                  {weekendBars.length > 0 ? (
                    <ChartBlock
                      headline="Weekend vs weekday listening"
                      subtitle={
                        chartCap.weekend?.trim() ||
                        weekend?.detail ||
                        "How your listening splits between weekends and weekdays."
                      }
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
