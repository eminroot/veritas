import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Routes, Route } from "react-router-dom";
import { useEffect, useRef } from "react";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { TourProvider } from "@/components/tour/Tour";
import AppLayout from "@/components/layout/AppLayout";
import { AssistantLauncher } from "@/components/assistant/AssistantLauncher";
import ScrollToTop from "./components/ScrollToTop";

import Landing from "./pages/Landing";
import Donate from "./pages/Donate";
import Cause from "./pages/Cause";
import Project from "./pages/Project";
import MapPage from "./pages/MapPage";
import Organisations from "./pages/Organisations";
import About from "./pages/About";
import HowItWorks from "./pages/HowItWorks";
import { Terms, Privacy } from "./pages/Legal";
import NotFound from "./pages/NotFound";

import Login from "./pages/Login";
import SignUp from "./pages/SignUp";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import Onboarding from "./pages/Onboarding";

import Dashboard from "./pages/Dashboard";
import Donations from "./pages/Donations";
import OrgProfile from "./pages/OrgProfile";
import OrgProjects from "./pages/OrgProjects";
import Settings from "./pages/Settings";
import Assistant from "./pages/Assistant";
import PortfolioProject from "./pages/PortfolioProject";
import ProjectPlanner from "./pages/ProjectPlanner";

// The design language, ported from MuhAI through BestByte. Order matters only between
// the two that share selectors: the console skin after the auth field rules it
// overrides inside `.app-shell`.
import "./styles/landing.css";
import "./styles/auth.css";
import "./styles/console.css";
import "./styles/tour.css";
import "./styles/veritas.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 30 * 60 * 1000,
      refetchOnWindowFocus: false,
      refetchOnMount: false,
      refetchOnReconnect: true,
      retry: (failureCount, error) => {
        // 4xx answers will not change on retry; an unreachable API is reported at once.
        const e = error as { status?: number; offline?: boolean };
        const status = Number(e?.status ?? 0);
        if (status >= 400 && status < 500) return false;
        if (e?.offline) return false;
        return failureCount < 2;
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 4000),
    },
  },
});

/** Each account sees only its own records: clear the cache when the account changes. */
function CacheScope() {
  const { user } = useAuth();
  const client = useQueryClient();
  const last = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    const id = user?.id ?? null;
    if (last.current !== undefined && last.current !== id) client.clear();
    last.current = id;
  }, [user?.id, client]);
  return null;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <CacheScope />
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <TourProvider>
            <ScrollToTop />
            <Routes>
              {/* Public site */}
              <Route path="/" element={<Landing />} />
              <Route path="/donate" element={<Donate />} />
              <Route path="/causes/:cause" element={<Cause />} />
              <Route path="/projects/:projectId" element={<Project />} />
              <Route path="/map" element={<MapPage />} />
              <Route path="/organisations" element={<Organisations />} />
              <Route path="/about" element={<About />} />
              <Route path="/how-it-works" element={<HowItWorks />} />
              <Route path="/terms" element={<Terms />} />
              <Route path="/privacy" element={<Privacy />} />
              <Route path="/pricing" element={<Navigate to="/organisations" replace />} />

              {/* Accounts */}
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<SignUp />} />
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/reset-password" element={<ResetPassword />} />
              {/* Outside ProtectedRoute: that guard is what sends people here. */}
              <Route path="/onboarding" element={<Onboarding />} />

              {/* The signed-in console */}
              <Route
                element={
                  <ProtectedRoute>
                    <AppLayout />
                  </ProtectedRoute>
                }
              >
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/donations" element={<Donations />} />
                <Route path="/organisation" element={<OrgProfile />} />
                <Route path="/organisation/projects" element={<OrgProjects />} />
                <Route path="/organisation/projects/plan/:projectId" element={<ProjectPlanner />} />
                <Route path="/organisation/projects/:projectId" element={<PortfolioProject view="org" />} />
                <Route path="/portfolio/:projectId" element={<PortfolioProject />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/assistant" element={<Assistant />} />
              </Route>

              <Route path="*" element={<NotFound />} />
            </Routes>
            <AssistantLauncher />
          </TourProvider>
        </BrowserRouter>
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
