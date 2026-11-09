import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { readOrgDraft } from "@/lib/orgDraft";

/**
 * The signed-in console's door. In order: signed in at all; email verified (a password
 * account has to click the link first, Google accounts are verified already); donor or
 * organisation chosen; and for an organisation, its details sent or at least saved. Each
 * missing step sends the person to the page that completes it, and back here after.
 */
export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading, accountType, api } = useAuth();
  const location = useLocation();

  // Only the Firebase session check blocks; it resolves from local storage, not the network.
  if (loading) {
    return (
      <div className="route-splash" role="status" aria-label="Loading">
        <Loader2 className="route-splash__spinner animate-spin" />
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!accountType) return <Navigate to="/onboarding" replace state={{ from: location.pathname }} />;

  const hasOrg = (api.status === "connected" && api.me.memberships.length > 0) || Boolean(readOrgDraft(user.id));
  if (accountType === "organisation" && !hasOrg) {
    // Only the API knows an organisation that applied elsewhere (or the demo one): ask it first.
    if (api.status === "idle" || api.status === "connecting") {
      return (
        <div className="route-splash" role="status" aria-label="Loading">
          <Loader2 className="route-splash__spinner animate-spin" />
        </div>
      );
    }
    return <Navigate to="/onboarding" replace />;
  }

  return <>{children}</>;
}
