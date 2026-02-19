import { Routes, Route } from "react-router";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Landing } from "./pages/Landing";
import { Register } from "./pages/Register";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { Settings } from "./pages/Settings";
import { DemoRealtime } from "./pages/DemoRealtime";
import { Activation } from "./pages/Activation";
import { ChatThread } from "./pages/ChatThread";
import { Notifications } from "./pages/Notifications";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Landing />} />
        <Route path="/register" element={<Register />} />
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
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
          path="/p/:projectId/chat"
          element={
            <ProtectedRoute>
              <ChatThread />
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
          path="/demo/realtime"
          element={
            <ProtectedRoute>
              <DemoRealtime />
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
    </Routes>
  );
}
