import React from "react";
import ReactDOM from "react-dom/client";
import { createHashRouter, RouterProvider } from "react-router-dom";
import { AppShell } from "./AppShell";
import { HubPage } from "./hub/HubPage";
import { ReplayPage } from "./replay/ReplayPage";
import { LivePage } from "./live/LivePage";
import { LeaderboardPage } from "./leaderboard/LeaderboardPage";
import "./styles/global.css";

// Hash router: the SPA is served by a plain static mount, so deep links
// must not require server-side route handling.
const router = createHashRouter([
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <HubPage /> },
      { path: "/replay", element: <ReplayPage /> },
      { path: "/live", element: <LivePage /> },
      { path: "/leaderboard", element: <LeaderboardPage /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
