import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function Register() {
  const { user, register, error } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [loading, setLoading] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    const ok = await register(form.email, form.password, form.name);
    setLoading(false);
    if (ok) nav("/");
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-8 bg-zinc-50">
      <div className="w-full max-w-sm bg-white border border-zinc-200 rounded-lg p-8">
        <h2 className="font-display font-bold text-2xl mb-1">Create account</h2>
        <p className="text-sm text-zinc-500 mb-6">Start managing your student leads in minutes.</p>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <Label>Full name</Label>
            <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="register-name-input" />
          </div>
          <div>
            <Label>Email</Label>
            <Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="register-email-input" />
          </div>
          <div>
            <Label>Password</Label>
            <Input type="password" required minLength={6} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="register-password-input" />
          </div>
          {error && <div className="text-sm text-red-600" data-testid="register-error">{error}</div>}
          <Button type="submit" disabled={loading} className="w-full bg-blue-600 hover:bg-blue-700" data-testid="register-submit-btn">
            {loading ? "Creating…" : "Create account"}
          </Button>
        </form>
        <p className="text-sm text-zinc-500 mt-5 text-center">
          Already have an account? <Link to="/login" className="text-blue-600 font-medium" data-testid="goto-login-link">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
