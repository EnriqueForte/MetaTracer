"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BookOpen, GitCompare, History, LayoutDashboard, Layers, Menu, Plug, Radar, Search, Shield, Users, Webhook } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { CommandPalette, ShortcutsHelp } from "@/components/shell/command-palette";
import { MaintainerCredit } from "@/components/shell/maintainer-credit";
import { ThemeSwitcher } from "@/components/shell/theme-switcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiFetch, parseNotifications, truncate, type NotificationItem } from "@/lib/api/browser";
import { ApiError } from "@/lib/api/errors";
import { APP_VERSION, BASE_PATH } from "@/lib/constants";
import { isTypingTarget } from "@/lib/keyboard";
import { queryKeys } from "@/lib/query/keys";
import { actorOf, useSession, useSessionQuery } from "@/lib/session";
import { formatRelative } from "@/lib/time";

const NAV = [
  { href: "/dashboard", label: "Panel", icon: LayoutDashboard },
  { href: "/", label: "Nuevo escaneo", icon: Radar },
  { href: "/search", label: "Buscar", icon: Search },
  { href: "/runs", label: "Historial", icon: History },
  { href: "/runs/compare", label: "Comparar", icon: GitCompare },
  { href: "/investigations", label: "Investigaciones", icon: Layers },
  { href: "/scopes", label: "Alcances", icon: Shield },
] as const;

/** Visible to operators (and with auth off); the API rejects viewers anyway. */
const OPERATOR_NAV = [
  { href: "/users", label: "Usuarios", icon: Users },
  { href: "/webhooks", label: "Webhooks", icon: Webhook },
  { href: "/integrations", label: "Integraciones", icon: Plug },
  { href: "/knowledge", label: "Conocimiento", icon: BookOpen },
] as const;

const NOTIFICATIONS_KEY = queryKeys.notifications;

const ETHICS_TEXT =
  "Solo uso autorizado: audita únicamente objetivos que te pertenezcan o que tengas permiso explícito para probar.";

function kindLabel(kind: NotificationItem["kind"]): string {
  if (kind === "failed") return "Escaneo fallido";
  if (kind === "aborted") return "Escaneo abortado";
  return "Escaneo completado";
}

const ALL_NAV_HREFS = [...NAV, ...OPERATOR_NAV].map((item) => item.href);

function isNavCurrent(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  const matches = ALL_NAV_HREFS.filter(
    (item) => item !== "/" && (pathname === item || pathname.startsWith(`${item}/`)),
  );
  matches.sort((left, right) => right.length - left.length);
  return matches[0] === href;
}

async function fetchNotifications(): Promise<NotificationItem[]> {
  const response = await apiFetch("/api/notifications");
  if (!response.ok) throw new ApiError(response.status, "No se pudieron cargar las notificaciones.");
  const parsed = parseNotifications(await response.json());
  if (parsed === null) throw new ApiError(200, "No se pudieron cargar las notificaciones.");
  return parsed;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const panelId = useId();
  const ethicsId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [narrow, setNarrow] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [ethicsOpen, setEthicsOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const sessionQuery = useSessionQuery();
  const session = useSession();
  const actor = actorOf(session);
  const notesQuery = useQuery({ queryKey: NOTIFICATIONS_KEY, queryFn: fetchNotifications });
  const notes = notesQuery.data ?? [];

  const networkDown = sessionQuery.isError && !(sessionQuery.error instanceof ApiError);
  const apiStatus = sessionQuery.isPending ? "checking" : networkDown ? "unreachable" : "reachable";
  const notesError = notesQuery.isError
    ? notesQuery.error instanceof ApiError
      ? "No se pudieron cargar las notificaciones."
      : "Error de red: la API no está accesible."
    : "";

  useEffect(() => {
    if (sessionQuery.isSuccess && sessionQuery.data.status === "signed-out") router.replace("/login");
  }, [router, sessionQuery.isSuccess, sessionQuery.data]);

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
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setHelpOpen(false);
        setPaletteOpen((open) => !open);
        return;
      }
      if (event.key === "?" && !event.ctrlKey && !event.metaKey && !event.altKey && !isTypingTarget(event.target)) {
        event.preventDefault();
        setPaletteOpen(false);
        setHelpOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!notesOpen) return;
    const onPointer = (event: MouseEvent) => {
      if (!panelRef.current?.contains(event.target as Node)) setNotesOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, [notesOpen]);

  const showUsers = actor === "operator";

  async function dismiss(id: number) {
    try {
      const response = await apiFetch(`/api/notifications/${id}`, { method: "DELETE" });
      if (response.ok || response.status === 404) {
        await queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
      }
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
        Ir al contenido principal
      </a>
      <div className="mt-shell">
        <aside
          id="app-sidebar"
          className={navOpen ? "mt-sidebar mt-sidebar-open" : "mt-sidebar"}
          inert={narrow && !navOpen ? true : undefined}
        >
          <Link href="/" className="mt-brand" aria-label="Inicio de MetaTracer" onClick={() => setNavOpen(false)}>
            <span className="mt-brand-row">
              <span className="mt-brand-mark" aria-hidden="true" />
              <span className="mt-brand-name">
                MetaTracer <span className="text-xs font-normal text-mt-faint">v{APP_VERSION}</span>
              </span>
            </span>
            <span className="mt-brand-sub">Inteligencia de seguridad</span>
          </Link>
          <nav className="flex flex-col" aria-label="Principal">
            <p id="nav-research" className="mt-nav-label">
              Investigación
            </p>
            <div role="group" aria-labelledby="nav-research">
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
            </div>
            {showUsers ? (
              <>
                <p id="nav-admin" className="mt-nav-label">
                  Administración
                </p>
                <div role="group" aria-labelledby="nav-admin">
                  {OPERATOR_NAV.map((item) => {
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
                </div>
              </>
            ) : null}
          </nav>
          <div className="mt-auto flex flex-col gap-1 px-2.5 pt-4">
            <span className="mt-kicker">Tema</span>
            <ThemeSwitcher />
          </div>
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
              Menú
            </Button>
            <div className="relative">
              <button
                type="button"
                className="mt-ethics"
                aria-expanded={ethicsOpen}
                aria-controls={ethicsId}
                title={ETHICS_TEXT}
                onClick={() => setEthicsOpen((open) => !open)}
              >
                Solo uso autorizado
              </button>
              {ethicsOpen ? (
                <p id={ethicsId} className="mt-ethics-detail">
                  {ETHICS_TEXT}
                </p>
              ) : null}
            </div>
            <Button
              variant="ghost"
              className="py-1 text-xs"
              aria-keyshortcuts="Control+K Meta+K"
              onClick={() => setPaletteOpen(true)}
            >
              Ir a… <span className="mt-tech text-mt-faint">Ctrl K</span>
            </Button>
            <MaintainerCredit />
            <div className="mt-session ml-auto">
              <p className="mt-status" role="status">
                <span
                  className="mt-status-dot"
                  data-state={apiStatus === "reachable" ? "ok" : apiStatus === "unreachable" ? "down" : undefined}
                  aria-hidden="true"
                />
                {apiStatus === "reachable"
                  ? "API accesible"
                  : apiStatus === "unreachable"
                    ? "API no accesible"
                    : "Comprobando API"}
              </p>
              <div className="relative" ref={panelRef}>
                <Button
                  variant="ghost"
                  className="py-1"
                  aria-label="Notificaciones"
                  aria-haspopup="true"
                  aria-expanded={notesOpen}
                  aria-controls={panelId}
                  onClick={() => {
                    setNotesOpen((open) => {
                      const next = !open;
                      if (next) void notesQuery.refetch();
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
                    aria-label="Panel de notificaciones"
                    className="absolute right-0 z-20 mt-2 max-h-96 w-80 overflow-y-auto rounded-md border border-mt-border bg-mt-surface p-3"
                  >
                    <div className="mb-2 flex items-center justify-between gap-2 border-b border-mt-border pb-2">
                      <h2 className="text-sm font-semibold text-mt-fg">Notificaciones</h2>
                      <Button variant="ghost" onClick={() => void notesQuery.refetch()}>
                        Actualizar
                      </Button>
                    </div>
                    {notesError ? (
                      <p className="text-sm text-mt-danger" role="status">
                        {notesError}
                      </p>
                    ) : null}
                    {!notesError && notes.length === 0 ? (
                      <p className="text-xs text-mt-muted">Aún no hay notificaciones.</p>
                    ) : null}
                    {notes.map((entry) => {
                      const when = entry.created_at ? formatRelative(entry.created_at) : "";
                      const body = (
                        <>
                          <Badge variant={entry.kind}>
                            {kindLabel(entry.kind)} — {entry.target}
                          </Badge>
                          <span className="mt-1 block text-xs text-mt-muted">
                            {entry.total_assets} recurso(s) · {entry.total_findings} hallazgo(s)
                            {when ? ` · ${when}` : ""}
                          </span>
                          {entry.error_message && (entry.kind === "failed" || entry.kind === "aborted") ? (
                            <span className="mt-1 block text-xs break-words text-mt-muted">
                              {truncate(entry.error_message, 150)}
                            </span>
                          ) : null}
                        </>
                      );
                      return (
                        <div
                          key={entry.id}
                          className="flex items-start justify-between gap-2 border-b border-mt-border py-3"
                        >
                          {entry.run_id ? (
                            <Link
                              href={`/runs/${encodeURIComponent(entry.run_id)}`}
                              className="min-w-0 rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-mt-focus"
                              onClick={() => setNotesOpen(false)}
                            >
                              {body}
                            </Link>
                          ) : (
                            <div className="min-w-0">{body}</div>
                          )}
                          {actor === "operator" ? (
                            <Button
                              variant="ghost"
                              aria-label="Descartar notificación"
                              onClick={() => void dismiss(entry.id)}
                            >
                              Descartar
                            </Button>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </div>
              {session.status === "signed-in" ? (
                <>
                  <p className="mt-session-meta">
                    <strong className="font-semibold text-mt-fg">{session.username}</strong>
                    <span> · {session.role === "operator" ? "operador" : "visor"}</span>
                  </p>
                  <p className="mt-session-note">
                    Cerrar sesión termina esta sesión en todas las superficies.
                  </p>
                  <Button variant="ghost" className="shrink-0 py-1" onClick={() => void signOut()}>
                    Cerrar sesión
                  </Button>
                </>
              ) : null}
            </div>
          </header>
          <main id="main-content" className="mt-content">
            {children}
          </main>
          <CommandPalette
            open={paletteOpen}
            onOpenChange={setPaletteOpen}
            actor={actor}
            onNavigate={(href) => router.push(href)}
          />
          <ShortcutsHelp open={helpOpen} onOpenChange={setHelpOpen} />
          <footer className="flex flex-col gap-2 px-6 pb-6">
            <p className="text-xs text-mt-muted">
              Auditoría pasiva de metadatos en documentos públicos dentro del alcance confirmado. No
              es una prueba de explotación.
            </p>
            <p className="flex flex-wrap gap-3 text-xs text-mt-muted">
              <button type="button" className="underline" onClick={() => setHelpOpen(true)}>
                Atajos de teclado (?)
              </button>
            </p>
          </footer>
        </div>
      </div>
    </>
  );
}
