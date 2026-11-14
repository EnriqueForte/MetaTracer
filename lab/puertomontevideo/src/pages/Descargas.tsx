export function DescargasPage() {
  return (
    <article className="manifiesto">
      <h2>Kit de prensa</h2>
      <p>Archivos de esta edición, todos sintéticos.</p>
      <ul>
        <li>
          <span className="kind">JPG</span>
          <a href="/media/grua4.jpg">Aéreo del puerto (grua4.jpg)</a>
        </li>
        <li>
          <span className="kind">JPG</span>
          <a href="/media/rambla.jpg">Rambla 25 de Agosto (rambla.jpg)</a>
        </li>
        <li>
          <span className="kind">PNG</span>
          <a href="/media/bahia.png">Dársenas 2019 (bahia.png)</a>
        </li>
        <li>
          <span className="kind">WebP</span>
          <a href="/media/mercado.webp">Mercado del Puerto (mercado.webp)</a>
        </li>
        <li>
          <span className="kind">GIF</span>
          <a href="/media/marea.gif">Loop de dársenas (marea.gif)</a>
        </li>
        <li>
          <span className="kind">SVG</span>
          <a href="/media/marca.svg">Marca de cabecera (marca.svg)</a>
        </li>
        <li>
          <span className="kind">PDF</span>
          <a href="/media/acta-terminal.pdf">Acta de la terminal</a>
        </li>
        <li>
          <span className="kind">DOCX</span>
          <a href="/media/junta.docx">Notas de la junta</a>
        </li>
        <li>
          <span className="kind">ODT</span>
          <a href="/media/bitacora.odt">Bitácora de muelle</a>
        </li>
      </ul>
    </article>
  );
}
