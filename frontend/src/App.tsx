import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AuthGate } from "./components/AuthGate";
import { AppShell } from "./components/layout/AppShell";
import { initTelegram } from "./lib/telegram";
import { Home } from "./screens/Home";
import { ProjectScreen } from "./screens/Project";
import { ReviewQueue } from "./screens/ReviewQueue";
import { Settings } from "./screens/Settings";
import { Voices } from "./screens/Voices";

export default function App() {
  useEffect(() => {
    initTelegram();
  }, []);

  return (
    <AuthGate>
      <AppShell>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/projects/:projectId" element={<ProjectScreen />} />
          <Route path="/projects/:projectId/review" element={<ReviewQueue />} />
          <Route path="/voices" element={<Voices />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </AuthGate>
  );
}
