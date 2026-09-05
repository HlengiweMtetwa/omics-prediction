"use client";

import { useEffect, useState } from "react";
import { useAuth, useRequireAuth } from "@/lib/auth-context";
import { api, AdminUser, ApiError } from "@/lib/api";
import AppShell from "@/components/AppShell";

const ASSIGNABLE_ROLES = [
  "researcher",
  "laboratory_scientist",
  "public_health_official",
  "student",
  "viewer",
];

const STATUS_COLOR: Record<string, string> = {
  active: "var(--status-good)",
  disabled: "var(--status-critical)",
};

export default function AdminPage() {
  const { token, loading: authLoading } = useRequireAuth();
  const { user } = useAuth();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [busyRows, setBusyRows] = useState<Record<string, boolean>>({});

  function refresh() {
    if (!token) return;
    api
      .listAdminUsers(token)
      .then(setUsers)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load users."));
  }

  useEffect(refresh, [token]);

  async function handleRoleChange(userId: string, role: string) {
    if (!token) return;
    setRowErrors((prev) => ({ ...prev, [userId]: "" }));
    setBusyRows((prev) => ({ ...prev, [userId]: true }));
    try {
      await api.changeUserRole(token, userId, role);
      refresh();
    } catch (err) {
      setRowErrors((prev) => ({
        ...prev,
        [userId]: err instanceof ApiError ? err.message : "Could not change role.",
      }));
    } finally {
      setBusyRows((prev) => ({ ...prev, [userId]: false }));
    }
  }

  async function handleToggleStatus(target: AdminUser) {
    if (!token) return;
    setRowErrors((prev) => ({ ...prev, [target.id]: "" }));
    setBusyRows((prev) => ({ ...prev, [target.id]: true }));
    try {
      if (target.status === "active") {
        await api.disableUser(token, target.id);
      } else {
        await api.enableUser(token, target.id);
      }
      refresh();
    } catch (err) {
      setRowErrors((prev) => ({
        ...prev,
        [target.id]: err instanceof ApiError ? err.message : "Could not change account status.",
      }));
    } finally {
      setBusyRows((prev) => ({ ...prev, [target.id]: false }));
    }
  }

  if (authLoading || !token) return null;

  if (user && user.role !== "administrator") {
    return (
      <AppShell>
        <div className="text-sm" style={{ color: "var(--status-critical)" }}>
          This page requires the Administrator role.
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
          Users
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
          Manage roles and account status. Administrator accounts can only be granted or changed
          from the command line (<code>scripts/create_admin.py</code>), never from this page.
        </p>
      </div>

      {error && (
        <div className="text-sm mb-4" style={{ color: "var(--status-critical)" }}>
          {error}
        </div>
      )}
      {users === null && !error && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          Loading…
        </div>
      )}

      {users && (
        <div className="flex flex-col gap-3">
          {users.map((u) => {
            const isAdmin = u.role === "administrator";
            const isSelf = u.id === user?.id;
            const locked = isAdmin;
            const busy = !!busyRows[u.id];
            return (
              <div
                key={u.id}
                className="rounded-xl border p-4"
                style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
              >
                <div className="flex items-center justify-between gap-4 flex-wrap">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                        {u.full_name}
                      </span>
                      {isSelf && (
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                          (you)
                        </span>
                      )}
                      <span
                        className="text-xs font-mono px-2 py-0.5 rounded-full"
                        style={{ background: "var(--page-plane)", color: STATUS_COLOR[u.status] }}
                      >
                        {u.status}
                      </span>
                    </div>
                    <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                      {u.email}
                      {u.institution ? ` · ${u.institution}` : ""}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {isAdmin ? (
                      <span
                        className="text-xs font-mono px-2 py-1 rounded-md"
                        style={{ background: "var(--page-plane)", color: "var(--text-secondary)" }}
                      >
                        administrator
                      </span>
                    ) : (
                      <select
                        aria-label={`Role for ${u.email}`}
                        value={u.role}
                        disabled={busy}
                        onChange={(e) => handleRoleChange(u.id, e.target.value)}
                        className="rounded-md border px-2 py-1.5 text-sm outline-none disabled:opacity-60"
                        style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
                      >
                        {ASSIGNABLE_ROLES.map((r) => (
                          <option key={r} value={r}>
                            {r.replace(/_/g, " ")}
                          </option>
                        ))}
                      </select>
                    )}
                    <button
                      onClick={() => handleToggleStatus(u)}
                      disabled={locked || busy}
                      className="text-xs font-medium px-3 py-1.5 rounded-md border disabled:opacity-40"
                      style={{
                        borderColor: "var(--gridline)",
                        color: u.status === "active" ? "var(--status-critical)" : "var(--status-good)",
                      }}
                      title={locked ? "Administrator accounts are managed from the command line" : undefined}
                    >
                      {u.status === "active" ? "Disable" : "Enable"}
                    </button>
                  </div>
                </div>
                {rowErrors[u.id] && (
                  <div className="text-xs mt-2" style={{ color: "var(--status-critical)" }}>
                    {rowErrors[u.id]}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
