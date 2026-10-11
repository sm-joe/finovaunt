import React from "react";
import { createRoot } from "react-dom/client";
import AuthenticatedShell from "./AuthenticatedShell";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthenticatedShell />
  </React.StrictMode>,
);
