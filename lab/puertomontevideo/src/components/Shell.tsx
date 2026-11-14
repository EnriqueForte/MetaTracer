import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Credit } from "./Credit";

const NAV = [
  { to: "/", label: "Portada", end: true },
  { to: "/acta.html", label: "Acta", end: false },
  { to: "/fotogaleria.html", label: "Fotogalería", end: false },
  { to: "/redaccion.html", label: "Redacción", end: false },
  { to: "/descargas.html", label: "Descargas", end: false },
] as const;

function Chrome({ nav, children }: { nav: ReactNode; children: ReactNode }) {
  return (
    <>
      <div className="harbor-stripe" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
      </div>
      <div className="lab-banner">
        Laboratorio de MetaTracer. Este sitio es <strong>ficticio</strong>: no
        es un medio de prensa, no es la ANP ni Montecon, y no representa a
        ninguna autoridad. Solo sirve para probar detección de metadata.
      </div>
      <header className="masthead">
        <p className="masthead-kicker">Ciudad Vieja / Rambla 25 de Agosto / TCP</p>
        <h1>
          <a href="/">Puertomontevideo</a>
        </h1>
        <div className="masthead-meta">
          <span>Sábado 14 de noviembre de 2026</span>
          <span id="js-stamp">Año I, n.º 12</span>
        </div>
      </header>
      <nav className="sections" aria-label="Secciones">
        {nav}
      </nav>
      <main className="wrap">{children}</main>
      <footer className="site">
        <p>
          Semanario inventado para un laboratorio. Textos y actas son ficción;
          muelles y barrios de Montevideo son reales. Fotos Wikimedia Commons.
        </p>
        <Credit />
      </footer>
    </>
  );
}

export function Shell() {
  return (
    <Chrome
      nav={NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => (isActive ? "is-current" : undefined)}
        >
          {item.label}
        </NavLink>
      ))}
    >
      <Outlet />
    </Chrome>
  );
}

export function StaticShell({
  children,
  current,
}: {
  children: ReactNode;
  current: (typeof NAV)[number]["to"];
}) {
  return (
    <Chrome
      nav={NAV.map((item) => (
        <a
          key={item.to}
          href={item.to === "/" ? "/" : item.to}
          className={item.to === current ? "is-current" : undefined}
          aria-current={item.to === current ? "page" : undefined}
        >
          {item.label}
        </a>
      ))}
    >
      {children}
    </Chrome>
  );
}
