import { useState } from "react";
import { Navigate, useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { GraduationCap } from "lucide-react";

export default function Login() {
  const { user, login, error } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("admin@leadflow.com");
  const [password, setPassword] = useState("admin123");
  const [loading, setLoading] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    const ok = await login(email, password);
    setLoading(false);
    if (ok) nav("/");
  };

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex flex-col justify-between w-1/2 bg-zinc-900 text-white p-12">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-md bg-blue-600 flex items-center justify-center">
            <GraduationCap className="w-5 h-5" strokeWidth={1.75} />
          </div>
          <div className="font-display font-bold">LeadFlow</div>
        </div>
        <div>
          <h1 className="font-display font-bold text-5xl leading-tight">
            Turn every<br/>student lead into<br/>a success story.
          </h1>
          <p className="mt-6 text-zinc-400 max-w-md">
            One inbox for WhatsApp outreach, AI follow-up calls in native languages, and a visual pipeline from first touch to enrollment.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-6 text-sm text-zinc-400">
          <div><div className="text-2xl font-display font-bold text-white">7</div>pipeline stages</div>
          <div><div className="text-2xl font-display font-bold text-white">2</div>languages (EN / HI)</div>
          <div><div className="text-2xl font-display font-bold text-white">∞</div>follow-ups</div>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <h2 className="font-display font-bold text-3xl mb-1">Sign in</h2>
          <p className="text-sm text-zinc-500 mb-6">Welcome back &mdash; let&apos;s close some leads.</p>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <Label>Email</Label>
              <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} data-testid="login-email-input" />
            </div>
            <div>
              <Label>Password</Label>
              <Input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} data-testid="login-password-input" />
            </div>
            {error && <div className="text-sm text-red-600" data-testid="login-error">{error}</div>}
            <Button type="submit" disabled={loading} className="w-full bg-blue-600 hover:bg-blue-700" data-testid="login-submit-btn">
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <p className="text-sm text-zinc-500 mt-6 text-center">
            No account? <Link to="/register" className="text-blue-600 font-medium" data-testid="goto-register-link">Create one</Link>
          </p>
          <div className="mt-8 p-3 rounded-md bg-zinc-50 border border-zinc-200 text-xs text-zinc-600">
            <div className="font-medium text-zinc-900 mb-1">Demo credentials</div>
            admin@leadflow.com / admin123
          </div>
        </div>
      </div>
    </div>
  );
}
