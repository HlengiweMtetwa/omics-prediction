"use client";

import { useState, FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";

const SELF_REGISTERABLE_ROLES = [
  "researcher",
  "laboratory_scientist",
  "public_health_official",
  "student",
  "viewer",
];

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [institution, setInstitution] = useState("");
  const [role, setRole] = useState("researcher");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setSubmitting(true);
    try {
      await api.register({
        full_name: fullName,
        email,
        password,
        institution: institution || undefined,
        role,
      });
      setSuccess(true);
      setTimeout(() => router.push("/login"), 1200);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--page-plane)" }}>
      <div
        className="w-full max-w-sm rounded-2xl border p-8"
        style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
      >
        <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
          Create an account
        </h1>
        <p className="text-sm mt-1 mb-6" style={{ color: "var(--text-secondary)" }}>
          Administrator accounts are not self-service.
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Field id="fullName" label="Full name">
            <input
              id="fullName"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className={inputClass}
              style={inputStyle}
            />
          </Field>
          <Field id="email" label="Email">
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
              style={inputStyle}
            />
          </Field>
          <Field id="institution" label="Institution (optional)">
            <input
              id="institution"
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
              className={inputClass}
              style={inputStyle}
            />
          </Field>
          <Field id="role" label="Role">
            <select
              id="role"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className={inputClass}
              style={inputStyle}
            >
              {SELF_REGISTERABLE_ROLES.map((r) => (
                <option key={r} value={r}>
                  {r.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </Field>
          <Field id="password" label="Password">
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
              style={inputStyle}
            />
          </Field>
          <Field id="confirmPassword" label="Confirm password">
            <input
              id="confirmPassword"
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={inputClass}
              style={inputStyle}
            />
          </Field>

          {error && (
            <div
              className="text-sm rounded-lg px-3 py-2"
              style={{ background: "color-mix(in oklab, var(--status-critical) 12%, transparent)", color: "var(--status-critical)" }}
            >
              {error}
            </div>
          )}
          {success && (
            <div
              className="text-sm rounded-lg px-3 py-2"
              style={{ background: "color-mix(in oklab, var(--status-good) 12%, transparent)", color: "var(--status-good)" }}
            >
              Account created. Redirecting to login…
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg px-3 py-2 text-sm font-medium text-white mt-2 disabled:opacity-60"
            style={{ background: "var(--series-1)" }}
          >
            {submitting ? "Creating…" : "Register"}
          </button>
        </form>

        <p className="text-sm mt-6 text-center" style={{ color: "var(--text-secondary)" }}>
          Already have an account?{" "}
          <Link href="/login" className="font-medium" style={{ color: "var(--series-1)" }}>
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}

const inputClass = "w-full rounded-lg border px-3 py-2 text-sm outline-none focus:ring-2";
const inputStyle = {
  borderColor: "var(--gridline)",
  background: "var(--page-plane)",
  color: "var(--text-primary)",
};

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>
        {label}
      </label>
      {children}
    </div>
  );
}
