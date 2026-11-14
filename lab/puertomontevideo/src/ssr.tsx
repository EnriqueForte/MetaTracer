import { renderToStaticMarkup } from "react-dom/server";
import { StaticShell } from "./components/Shell";
import { ActaPage } from "./pages/Acta";
import { DescargasPage } from "./pages/Descargas";
import { FotogaleriaPage } from "./pages/Fotogaleria";
import { HomePage } from "./pages/Home";
import { RedaccionPage } from "./pages/Redaccion";

export const pages: Record<string, string> = {
  "index.html": renderToStaticMarkup(
    <StaticShell current="/">
      <HomePage />
    </StaticShell>,
  ),
  "acta.html": renderToStaticMarkup(
    <StaticShell current="/acta.html">
      <ActaPage />
    </StaticShell>,
  ),
  "fotogaleria.html": renderToStaticMarkup(
    <StaticShell current="/fotogaleria.html">
      <FotogaleriaPage />
    </StaticShell>,
  ),
  "redaccion.html": renderToStaticMarkup(
    <StaticShell current="/redaccion.html">
      <RedaccionPage />
    </StaticShell>,
  ),
  "descargas.html": renderToStaticMarkup(
    <StaticShell current="/descargas.html">
      <DescargasPage />
    </StaticShell>,
  ),
};
