import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export default function ProtectedRoute({ children }) {
  const { user } = useAuth();
  if (user === null) {
    return (
      <div className="min-h-screen flex items-center justify-center text-zinc-500">
        Loading…
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}
