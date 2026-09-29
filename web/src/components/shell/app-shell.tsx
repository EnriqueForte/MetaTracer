"use client";

import { Bell, History, LayoutDashboard, Menu, Radar, Shield, Users } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  apiFetch,
  parseNotifications,
  parseSession,
  truncate,
  type NotificationItem,
  type SessionState,
} from "@/lib/api/browser";
import { APP_VERSION, BASE_PATH } from "@/lib/constants";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/", label: "Reconnaissance", icon: Radar },
  { href: "/runs", label: "History", icon: History },
  { href: "/scopes", label: "Scopes", icon: Shield },
] as const;

function kindLabel(kind: NotificationItem["kind"]): string {
  if (kind === "failed") return "Scan failed";
  if (kind === "aborted") return "Scan aborted";
  return "Scan completed";
}

function kindVariant(kind: NotificationItem["kind"]): "failed" | "aborted" | "completed" {
  if (kind === "failed") return "failed";
  if (kind === "aborted") return "aborted";
  return "completed";
}

function isNavCurrent(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const panelId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [narrow, setNarrow] = useState(false);
  const [session, setSession] = useState<SessionState>({ status: "loading" });
  const [notesOpen, setNotesOpen] = useState(false);
  const [notes, setNotes] = useState<NotificationItem[]>([]);
  const [notesError, setNotesError] = useState("");
  const [apiStatus, setApiStatus] = useState<"checking" | "reachable" | "unreachable">("checking");

  const loadSession = useCallback(async () => {
    try {
      const response = await apiFetch("/api/auth/me");
      setApiStatus("reachable");
      if (response.status === 401) {
        setSession({ status: "signed-out" });
        router.replace("/login");
        return;
      }
      if (!response.ok) {
        setSession({ status: "signed-out" });
        return;
      }
      setSession(parseSession(await response.json()));
    } catch {
      setApiStatus("unreachable");
      setSession({ status: "signed-out" });
    }
  }, [router]);

  const loadNotes = useCallback(async () => {
    try {
      const response = await apiFetch("/api/notifications");
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) {
        setNotesError("Could not load notifications.");
        return;
      }
      const parsed = parseNotifications(await response.json());
      if (parsed === null) {
        setNotesError("Could not load notifications.");
        return;
      }
      setNotes(parsed);
      setNotesError("");
    } catch {
      setNotesError("Network error: the API is unreachable.");
    }
  }, [router]);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 1023px)");
    const apply = () => {
      setNarrow(query.matches);
      if (!query.matches) setNavOpen(false);
    };
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    void loadSession();
    void loadNotes();
  }, [loadSession, loadNotes]);

  useEffect(() => {
    if (!notesOpen) return;
    const onPointer = (event: MouseEvent) => {
      if (!panelRef.current?.contains(event.target as Node)) setNotesOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, [notesOpen]);

  const showUsers =
    session.status === "auth-off" ||
    (session.status === "signed-in" && session.role === "operator");

  async function dismiss(id: number) {
    try {
      const response = await apiFetch(`/api/notifications/${id}`, { method: "DELETE" });
      if (response.ok || response.status === 404) await loadNotes();
    } catch {
      /* a failed delete never blocks the bell */
    }
  }

  async function signOut() {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch {
      /* the session is cleared server-side when the request lands */
    }
    window.location.assign(`${BASE_PATH}/login`);
  }

  return (
    <>
      <a className="mt-skip" href="#main-content">
        Skip to main content
      </a>
      <div className="mt-shell">
        <aside
          id="app-sidebar"
          className={navOpen ? "mt-sidebar mt-sidebar-open" : "mt-sidebar"}
          inert={narrow && !navOpen ? true : undefined}
        >
          <Link href="/" className="mt-brand" aria-label="MetaTracer home" onClick={() => setNavOpen(false)}>
            <span className="mt-brand-name">
              MetaTracer <span className="text-xs font-normal text-mt-faint">v{APP_VERSION}</span>
            </span>
            <span className="mt-brand-sub">Security Intelligence</span>
          </Link>
          <nav className="flex flex-col" aria-label="Primary">
            {NAV.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="mt-nav-link"
                  aria-current={isNavCurrent(item.href, pathname) ? "page" : undefined}
                  onClick={() => setNavOpen(false)}
                >
                  <Icon aria-hidden="true" className="size-4" />
                  {item.label}
                </Link>
              );
            })}
            {showUsers ? (
              <Link
                href="/users"
                className="mt-nav-link"
                aria-current={isNavCurrent("/users", pathname) ? "page" : undefined}
                onClick={() => setNavOpen(false)}
              >
                <Users aria-hidden="true" className="size-4" />
                Users
              </Link>
            ) : null}
          </nav>
        </aside>
        {navOpen && narrow ? (
          <div className="mt-scrim" onClick={() => setNavOpen(false)} aria-hidden="true" />
        ) : null}
        <div className="mt-main">
          <header className="mt-topbar">
            <Button
              variant="ghost"
              className="mt-menu-btn py-1"
              aria-expanded={navOpen}
              aria-controls="app-sidebar"
              onClick={() => setNavOpen((open) => !open)}
            >
              <Menu aria-hidden="true" className="size-4" />
              Menu
            </Button>
            <p className="mt-ethics">
              Authorized use only
              <span className="sr-only">
                {" "}
                — audit exclusively targets you own or are explicitly authorized to test.
              </span>
            </p>
            <div className="mt-session ml-auto">
              <p className="mt-status" role="status">
                <span
                  className="mt-status-dot"
                  data-state={apiStatus === "reachable" ? "ok" : apiStatus === "unreachable" ? "down" : undefined}
                  aria-hidden="true"
                />
                {apiStatus === "reachable"
                  ? "API reachable"
                  : apiStatus === "unreachable"
                    ? "API unreachable"
                    : "Checking API"}
              </p>
              <div className="relative" ref={panelRef}>
                <Button
                  variant="ghost"
                  className="py-1"
                  aria-label="Notifications"
                  aria-haspopup="true"
                  aria-expanded={notesOpen}
                  aria-controls={panelId}
                  onClick={() => {
                    setNotesOpen((open) => {
                      const next = !open;
                      if (next) void loadNotes();
                      return next;
                    });
                  }}
                >
                  <Bell aria-hidden="true" className="size-5" />
                  {notes.length > 0 ? (
                    <Badge variant="info" className="absolute -top-1 -right-1">
                      {notes.length}
                    </Badge>
                  ) : null}
                </Button>
                {notesOpen ? (
                  <div
                    id={panelId}
                    role="region"
                    aria-label="Notifications panel"
                    className="absolute right-0 z-20 mt-2 max-h-96 w-80 overflow-y-auto rounded-md border border-mt-border bg-mt-surface p-3"
                  >
                    <div className="mb-2 flex items-center justify-between gap-2 border-b border-mt-border pb-2">
                      <h2 className="text-sm font-semibold text-mt-fg">Notifications</h2>
                      <Button variant="ghost" onClick={() => void loadNotes()}>
                        Refresh
                      </Button>
                    </div>
                    {notesError ? (
                      <p className="text-sm text-mt-danger" role="status">
                        {notesError}
                      </p>
                    ) : null}
                    {!notesError && notes.length === 0 ? (
                      <p className="text-xs text-mt-muted">No notifications yet.</p>
                    ) : null}
                    {notes.map((entry) => (
                      <div
                        key={entry.id}
                        className="flex items-start justify-between gap-2 border-b border-mt-border py-3"
                      >
                        <div className="min-w-0">
                          <p>
                            <Badge variant={kindVariant(entry.kind)}>
                              {kindLabel(entry.kind)} — {entry.target}
                            </Badge>
                          </p>
                          <p className="mt-1 text-xs text-mt-muted">
                            {entry.total_assets} asset(s) · {entry.total_findings} finding(s)
                          </p>
                          {entry.error_message && (entry.kind === "failed" || entry.kind === "aborted") ? (
                            <p className="mt-1 text-xs break-words text-mt-muted">
                              {truncate(entry.error_message, 150)}
                            </p>
                          ) : null}
                        </div>
                        <Button
                          variant="ghost"
                          aria-label="Dismiss notification"
                          onClick={() => void dismiss(entry.id)}
                        >
                          Dismiss
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
              {session.status === "signed-in" ? (
                <>
                  <p className="mt-session-meta">
                    <strong className="font-semibold text-mt-fg">{session.username}</strong>
                    <span> · {session.role}</span>
                  </p>
                  <p className="mt-session-note">
                    Signing out also ends the session used by the classic UI.
                  </p>
                  <Button variant="ghost" className="py-1" onClick={() => void signOut()}>
                    Sign out
                  </Button>
                </>
              ) : null}
            </div>
          </header>
          <main id="main-content" className="mt-content">
            {children}
          </main>
          <footer className="flex flex-col gap-2 px-6 pb-6">
            <p className="text-xs text-mt-muted">
              Passive metadata audit of publicly available documents inside the confirmed scope. Not
              an exploitation test.
            </p>
            <p className="text-xs text-mt-muted">
              <a href="/" className="underline">
                Classic UI
              </a>
            </p>
          </footer>
        </div>
      </div>
    </>
  );
}
