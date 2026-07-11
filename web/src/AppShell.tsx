import { NavLink, Outlet } from "react-router-dom";
import "./AppShell.css";

export function AppShell() {
  return (
    <div className="shell">
      <header className="shell-header">
        <NavLink to="/" className="wordmark">
          bluffhouse
          <span className="wordmark-tag">bench</span>
        </NavLink>
        <nav className="shell-nav">
          <NavLink to="/" end>
            Home
          </NavLink>
          <NavLink to="/live">Play live</NavLink>
          <NavLink to="/leaderboard">Leaderboard</NavLink>
        </nav>
      </header>
      <div className="shell-body">
        <Outlet />
      </div>
    </div>
  );
}
