type HomeProps = {
  onLogout: () => void;
};

export function Home({ onLogout }: HomeProps) {
  const user = JSON.parse(localStorage.getItem("user")!);

  return (
    <div className="page">
      <h1>Hello, {user.displayName} </h1>

      <p>
        Last.fm user: <strong>{user.lastfmUsername}</strong>
      </p>

      <div className="card">
        <h2 style={{ marginTop: "0px" }}>Discover:</h2>
        <ul>
          <li>How your listening habits change and evolve</li>
          <li>When you are most active and how that varies over time</li>
          <li>Periods of musical exploration versus routine listening</li>
          <li>Shifts in taste, diversity, and artist preference</li>
        </ul>
      </div>
      <button>Fetch my Data</button>
      <button onClick={onLogout}>Log out</button>
    </div>
  );
}
