import { Routes, Route } from "react-router";
import { Layout } from "./components/Layout";
import { MobileShell } from "./components/MobileShell";
import { ChatShell } from "./components/ChatShell";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Landing } from "./pages/Landing";
import { Register } from "./pages/Register";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { Settings } from "./pages/Settings";
import { Updates } from "./pages/Updates";
import { DemoRealtime } from "./pages/DemoRealtime";
import { Activation } from "./pages/Activation";
import { Onboarding } from "./pages/Onboarding";
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
          path="/demo/realtime"
          element={
            <ProtectedRoute>
              <DemoRealtime />
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
          path="/p/:projectId/notifications"
          element={
            <ProtectedRoute>
              <Notifications />
            </ProtectedRoute>
          }
        />
      </Route>

      {/* App pages with bottom nav (mobile shell) */}
      <Route element={<MobileShell />}>
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

      {/* Immersive chat (no nav chrome) */}
      <Route element={<ChatShell />}>
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
