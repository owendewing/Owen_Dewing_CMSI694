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
      <p>
        Time zone: <strong>{user.timezone}</strong>
      </p>

      <div className="card">
        <h2>Next steps</h2>
        <ul>
          <li>Fetch listening history</li>
          <li>Analyze time-of-day patterns</li>
          <li>Detect taste shifts</li>
          <li>Visualize listening modes</li>
        </ul>
      </div>
      <button onClick={onLogout}>Log out</button>
    </div>
  );
}
