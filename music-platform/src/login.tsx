import { useState } from "react";
import { useNavigate } from "react-router-dom";

const timeZones = Intl.supportedValuesOf("timeZone");

export default function Login({ onLogin }: { onLogin: () => void }) {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [timezone, setTimezone] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone
  );
  const [displayName, setDisplayName] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    const user = {
      lastfmUsername: username,
      displayName: displayName || username,
      timezone,
      createdAt: new Date().toISOString(),
    };

    localStorage.setItem("user", JSON.stringify(user));
    onLogin();
    navigate("/");
  }

  return (
    <div className="page">
      <h1>Welcome 🎧</h1>
      <p>Analyze your listening habits using your Last.fm data.</p>

      <form onSubmit={handleSubmit} className="card">
        <label>
          Last.fm Username *
          <input
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="my username"
          />
        </label>

        <label>
          Display Name (optional)
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="my name"
          />
        </label>

        <label>
          Time Zone *
          <select
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
          >
            {timeZones.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
        </label>

        <button type="submit">Continue</button>
      </form>
    </div>
  );
}
