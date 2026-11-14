import { Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { ActaPage } from "./pages/Acta";
import { DescargasPage } from "./pages/Descargas";
import { FotogaleriaPage } from "./pages/Fotogaleria";
import { HomePage } from "./pages/Home";
import { RedaccionPage } from "./pages/Redaccion";

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/acta.html" element={<ActaPage />} />
        <Route path="/fotogaleria.html" element={<FotogaleriaPage />} />
        <Route path="/redaccion.html" element={<RedaccionPage />} />
        <Route path="/descargas.html" element={<DescargasPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
