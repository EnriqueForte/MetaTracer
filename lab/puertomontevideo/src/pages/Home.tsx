export function HomePage() {
  return (
    <>
      <article className="hero">
        <figure>
          <div className="frame frame--hero">
            <img
              src="/media/grua4.jpg"
              width={1280}
              height={720}
              alt="Vista aérea del puerto de Montevideo, con dársenas y Ciudad Vieja"
            />
          </div>
          <div className="hero-copy">
            <h2>Las grúas de TCP, contra el perfil del Cerro</h2>
            <p className="lede">
              En Terminal Cuenca del Plata el muelle C amaneció con el mismo
              ruido de spreader. Del otro lado de la bahía, El Cerro. A
              espaldas, Ciudad Vieja y la Rambla 25 de Agosto de 1825.
            </p>
            <figcaption>
              Puerto de Montevideo (Fedaro, Wikimedia Commons, CC BY-SA 4.0).
              EXIF GPS plantado por el lab.
            </figcaption>
          </div>
        </figure>
      </article>

      <section className="ledger">
        <article className="story">
          <a className="frame frame--rambla" href="/fotogaleria.html">
            <img
              src="/media/rambla.jpg"
              width={1200}
              height={675}
              alt="Puerto de Montevideo visto desde Ciudad Vieja"
            />
          </a>
          <h3>
            <a href="/fotogaleria.html">Rambla 25 de Agosto, viento sur</a>
          </h3>
          <p>
            De la peatonal Sarandí al Mercado del Puerto por Pérez Castellano.
            El Muelle Fluvial, el Muelle Maciel y la Capitanía quedan a una
            cuadra; hacia el oeste, Capurro y La Teja.
          </p>
        </article>
        <article className="story">
          <a className="frame frame--bahia" href="/acta.html">
            <img
              src="/media/bahia.png"
              width={1100}
              height={620}
              alt="Dársenas del puerto de Montevideo en 2019"
            />
          </a>
          <h3>
            <a href="/acta.html">El acta de la terminal, en PDF</a>
          </h3>
          <p>
            Junta ficticia de la Mesa del Muelle: TCP, Montecon, dársena
            fluvial, Capurro y La Teja. El cuerpo se inventó; la metadata no.
          </p>
        </article>
        <article className="story story--wide">
          <a className="frame frame--mercado" href="/fotogaleria.html">
            <img
              src="/media/mercado.webp"
              width={1000}
              height={560}
              alt="Mercado del Puerto en Pérez Castellano"
            />
          </a>
          <h3>
            <a href="/fotogaleria.html">Pérez Castellano, parrillas bajo el techo</a>
          </h3>
          <p>
            Del Mercado del Puerto a la peatonal Sarandí. El archivo WebP va
            limpio: el GPS y el IPTC están en las otras fotos de la edición.
          </p>
        </article>
      </section>

      <section className="manifiesto">
        <h3>Manifiesto de esta edición</h3>
        <ol>
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
          <li>
            <span className="kind">SVG</span>
            <a href="/media/marca.svg">Marca de la cabecera</a>
          </li>
          <li>
            <span className="kind">GIF</span>
            <a href="/media/marea.gif">Loop sobre las dársenas</a>
          </li>
          <li>
            <span className="kind">WebP</span>
            <a href="/media/mercado.webp">Mercado del Puerto</a>
          </li>
          <li>
            <span className="kind">Kit</span>
            <a href="/descargas.html">Prensa completa</a>
          </li>
        </ol>
      </section>
    </>
  );
}
