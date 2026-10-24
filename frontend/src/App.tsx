import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { DashboardPage } from "./pages/DashboardPage";
import { ExecutionPage } from "./pages/ExecutionPage";
import { HistoryPage } from "./pages/HistoryPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RoadmapPage } from "./pages/RoadmapPage";
import { SettingsPage } from "./pages/SettingsPage";
import { NotificationsProvider } from "./components/Notifications";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 3000,
      retry: 2,
      refetchOnWindowFocus: true,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <NotificationsProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<DashboardPage />} />
              <Route path="projects" element={<ProjectsPage />} />
              <Route path="execution" element={<ExecutionPage />} />
              <Route path="roadmap" element={<RoadmapPage />} />
              <Route path="history" element={<HistoryPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </NotificationsProvider>
    </QueryClientProvider>
  );
}
