import { useEffect, useState } from "react";
import { Link, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api";
import Home from "./components/Home";
import Login from "./components/Login";
import Register from "./components/Register";
import CreateRecord from "./components/CreateRecord";
import UpdateRecord from "./components/UpdateRecord";
import DeleteRecord from "./components/DeleteRecord";

// HW4 Part 1: top-level auth state (useState) lives here and is passed down
// as props to every routed component, per the spec's "pass props" requirement.
// useEffect checks for an existing session cookie on load (GET /api/hw4/auth/me)
// so a page refresh doesn't lose the logged-in state.
export default function App() {
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    api
      .me()
      .then((data) => setUser(data))
      .catch(() => setUser(null))
      .finally(() => setCheckingSession(false));
  }, []);

  async function handleLogout() {
    try {
      await api.logout();
    } finally {
      setUser(null);
      navigate("/");
    }
  }

  return (
    <div className="app">
      <nav className="nav">
        <Link to="/" className="brand">
          HW4: Grocery Recall Notices
        </Link>
        <div className="nav-links">
          {user ? (
            <>
              <span className="nav-user">{user.name}</span>
              <button type="button" onClick={handleLogout}>
                Log out
              </button>
            </>
          ) : (
            <>
              <Link to="/login">Log in</Link>
              <Link to="/register">Register</Link>
            </>
          )}
        </div>
      </nav>

      <main>
        {checkingSession ? (
          <div className="page">
            <p>Loading...</p>
          </div>
        ) : (
          <Routes>
            <Route path="/" element={<Home user={user} />} />
            <Route path="/login" element={<Login onLogin={setUser} />} />
            <Route path="/register" element={<Register onLogin={setUser} />} />
            <Route path="/create" element={<CreateRecord user={user} />} />
            <Route path="/update" element={<UpdateRecord user={user} />} />
            <Route path="/delete" element={<DeleteRecord user={user} />} />
          </Routes>
        )}
      </main>
    </div>
  );
}
