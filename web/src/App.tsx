import { Routes, Route } from "react-router";
import { Layout } from "./components/Layout";
import { AppShell } from "./components/shell/AppShell";
import { ChatAppShell } from "./components/shell/ChatAppShell";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Landing } from "./pages/Landing";
import { Register } from "./pages/Register";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { Settings } from "./pages/Settings";
import { Updates } from "./pages/Updates";
import { UpdatesPage } from "./pages/UpdatesPage";
import { Activation } from "./pages/Activation";
import { Onboarding } from "./pages/Onboarding";
import { OnboardingNotifications } from "./pages/OnboardingNotifications";
import { ChatThread } from "./pages/ChatThread";
import { Notifications } from "./pages/Notifications";
import { Admin } from "./pages/Admin";

export function App() {
  return (
    <Routes>
      {/* Auth / public pages keep top-nav Layout */}
      <Route element={<Layout />}>
        <Route path="/" element={<Landing />} />
        <Route path="/register" element={<Register />} />
        <Route path="/login" element={<Login />} />
        <Route
          path="/admin"
          element={
            <ProtectedRoute requiredRole="admin">
              <Admin />
            </ProtectedRoute>
          }
        />
        <Route
          path="/p/:projectId/activate"
          element={
            <ProtectedRoute>
              <Activation />
            </ProtectedRoute>
          }
        />
        <Route
          path="/p/:projectId/onboarding"
          element={
            <ProtectedRoute>
              <Onboarding />
            </ProtectedRoute>
          }
        />
        <Route
          path="/p/:projectId/onboarding/notifications"
          element={
            <ProtectedRoute>
              <OnboardingNotifications />
            </ProtectedRoute>
          }
        />
        <Route
          path="/p/:projectId/notifications"
          element={
            <ProtectedRoute>
              <Notifications />
            </ProtectedRoute>
          }
        />
        <Route
          path="/p/:projectId/updates"
          element={
            <ProtectedRoute>
              <UpdatesPage />
            </ProtectedRoute>
          }
        />
      </Route>

      {/* App pages with responsive shell (bottom nav or side rail) */}
      <Route element={<AppShell />}>
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/updates"
          element={
            <ProtectedRoute>
              <Updates />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <Settings />
            </ProtectedRoute>
          }
        />
      </Route>

      {/* Chat with responsive shell (immersive or split view) */}
      <Route element={<ChatAppShell />}>
        <Route
          path="/p/:projectId/chat"
          element={
            <ProtectedRoute>
              <ChatThread />
            </ProtectedRoute>
          }
        />
      </Route>
    </Routes>
  );
}
