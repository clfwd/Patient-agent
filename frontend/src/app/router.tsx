import { Routes, Route } from "react-router-dom";

import { WorkspacePage } from "@/app/workspace-page";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<WorkspacePage />} />
      <Route path="/sessions/:sessionId" element={<WorkspacePage />} />
    </Routes>
  );
}
