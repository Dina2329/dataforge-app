import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Boxes } from "lucide-react";
import { useLogin, useRegister } from "../hooks/useAuth";
import { apiErrorMessage } from "../lib/apiClient";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";

export function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const login = useLogin();
  const register = useRegister();
  const pending = login.isPending || register.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (mode === "login") {
        await login.mutateAsync({ email, password });
      } else {
        await register.mutateAsync({ email, name, password });
      }
      navigate("/");
    } catch (err) {
      setError(apiErrorMessage(err, "Could not sign in"));
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-canvas via-surface to-accent-secondary-tint px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <Boxes className="size-7 text-accent-secondary" />
          <span className="text-xl font-semibold text-ink-primary">DataForge</span>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-2xl bg-surface p-7 shadow-xl border border-border-default"
        >
          <h1 className="mb-1 text-lg font-semibold text-ink-primary">
            {mode === "login" ? "Welcome back" : "Create an account"}
          </h1>
          <p className="mb-6 text-sm text-ink-tertiary">
            {mode === "login" ? "Sign in to continue" : "Get started with DataForge"}
          </p>

          {mode === "register" && (
            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium text-ink-secondary">Name</label>
              <Input value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
          )}
          <div className="mb-3">
            <label className="mb-1 block text-xs font-medium text-ink-secondary">Email</label>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="mb-5">
            <label className="mb-1 block text-xs font-medium text-ink-secondary">Password</label>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
          </div>

          {error && (
            <div className="mb-4 rounded-lg bg-status-danger-tint px-3 py-2 text-sm text-status-danger">{error}</div>
          )}

          <Button type="submit" loading={pending} className="w-full">
            {mode === "login" ? "Sign in" : "Create account"}
          </Button>

          <button
            type="button"
            className="mt-4 w-full text-center text-xs text-ink-tertiary transition-colors hover:text-accent-secondary"
            onClick={() => setMode(mode === "login" ? "register" : "login")}
          >
            {mode === "login" ? "Need an account? Register" : "Already have an account? Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
