import React from "react";
import ReactDOM from "react-dom/client";
import { ReplayApp } from "./replay/ReplayApp";
import { embeddedPayload } from "./lib/data";
import "./styles/global.css";

// Entry for the self-contained replay.html: payload embedded at build marker,
// no router, works over file://.
const payload = embeddedPayload();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {payload ? (
      <ReplayApp payload={payload} standalone />
    ) : (
      <div style={{ padding: 40, color: "var(--muted)" }}>
        No replay data embedded — generate one with <code>bluffhouse demo</code> or{" "}
        <code>bluffhouse run</code>.
      </div>
    )}
  </React.StrictMode>,
);
