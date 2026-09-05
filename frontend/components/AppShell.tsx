"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/projects", label: "Projects" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const navItems =
    user?.role === "administrator" ? [...NAV_ITEMS, { href: "/admin", label: "Admin" }] : NAV_ITEMS;

  return (
    <div className="min-h-screen flex" style={{ background: "var(--page-plane)" }}>
      <aside
        className="w-60 shrink-0 border-r flex flex-col justify-between"
        style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
      >
        <div>
          <div className="px-5 py-5 border-b" style={{ borderColor: "var(--gridline)" }}>
            <div className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
              AI-WasteGuard
            </div>
            <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
              Environmental disease intelligence
            </div>
          </div>
          <nav className="px-3 py-4 flex flex-col gap-1">
            {navItems.map((item) => {
              const active = pathname?.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-lg px-3 py-2 text-sm font-medium transition-colors"
                  style={{
                    background: active ? "var(--page-plane)" : "transparent",
                    color: active ? "var(--text-primary)" : "var(--text-secondary)",
                  }}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {user && (
          <div className="px-4 py-4 border-t" style={{ borderColor: "var(--gridline)" }}>
            <div className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
              {user.full_name}
            </div>
            <div className="text-xs truncate" style={{ color: "var(--text-muted)" }}>
              {user.email}
            </div>
            <div
              className="mt-1 inline-block text-xs font-mono px-1.5 py-0.5 rounded"
              style={{ background: "var(--page-plane)", color: "var(--text-secondary)" }}
            >
              {user.role}
            </div>
            <button
              onClick={logout}
              className="mt-3 w-full text-sm rounded-lg border px-3 py-1.5 font-medium hover:bg-black/5 transition-colors"
              style={{ borderColor: "var(--gridline)", color: "var(--text-secondary)" }}
            >
              Log out
            </button>
          </div>
        )}
      </aside>

      <main className="flex-1 px-8 py-8 max-w-6xl mx-auto w-full">{children}</main>
    </div>
  );
}
