import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { MotionConfig } from "motion/react";
import "./index.css";
import { AuthProvider, useAuth } from "./components/Auth";
import { ToastProvider } from "./components/Toast";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Budgets from "./pages/Budgets";
import Insights from "./pages/Insights";
import Metrics from "./pages/Metrics";
import Goals from "./pages/Goals";
import Assistant from "./pages/Assistant";

function Protected({ children }) {
  const { user, ready } = useAuth();
  if (!ready) return <div className="grid h-full place-items-center"><div className="skeleton h-10 w-10 rounded-full" /></div>;
  return user ? children : <Navigate to="/login" replace />;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <ToastProvider>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route element={<Protected><Layout /></Protected>}>
                <Route index element={<Dashboard />} />
                <Route path="transactions" element={<Transactions />} />
                <Route path="budgets" element={<Budgets />} />
                <Route path="insights" element={<Insights />} />
                <Route path="metrics" element={<Metrics />} />
                <Route path="goals" element={<Goals />} />
                <Route path="assistant" element={<Assistant />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </AuthProvider>
        </ToastProvider>
      </BrowserRouter>
    </MotionConfig>
  </React.StrictMode>,
);
