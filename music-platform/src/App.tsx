import { Routes, Route, Navigate } from "react-router-dom";
import { useState } from "react";
import Login from "./login";
import { Home } from "./home";

function App() {
  const [user, setUser] = useState(() => localStorage.getItem("user"));

  const handleLogout = () => {
    localStorage.removeItem("user");
    setUser(null);
  };

  return (
    <Routes>
      <Route
        path="/login"
        element={
          <Login onLogin={() => setUser(localStorage.getItem("user"))} />
        }
      />
      <Route
        path="/"
        element={
          user ? (
            <Home onLogout={handleLogout} />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />
    </Routes>
  );
}

export default App;
