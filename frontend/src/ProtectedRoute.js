// ProtectedRoute — gates a route based on auth state.
//
// Three states from AuthContext:
//   loading=true            → render spinner (don't redirect yet)
//   loading=false, !user    → redirect to /login
//   loading=false, user OK  → render children (with onboarding/admin checks)

import { Navigate, useLocation } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth } from "./AuthContext";

export default function ProtectedRoute({ children, requireAdmin = false, allowUnonboarded = false }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="auth-loading" data-testid="protected-loading">
        <Loader2 className="spin" size={32} />
        <p className="mono">CHECKING…</p>
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (requireAdmin && user.role !== "admin") {
    return <Navigate to="/" replace state={{ adminBlocked: true }} />;
  }
  if (!user.onboarding_complete && !allowUnonboarded && location.pathname !== "/onboarding") {
    return <Navigate to="/onboarding" replace />;
  }
  return children;
}
