export function ActaPage() {
  return (
    <>
      <article className="ledger">
        <div className="story">
          <h2>Acta de la junta de la terminal</h2>
          <p className="lede">
            Extracto inventado de una junta de la Mesa del Muelle. No es un
            documento de la ANP, de Terminal Cuenca del Plata ni de Montecon.
          </p>
          <p>
            El texto nombra muelles A y B (Montecon), muelle C (TCP), Muelle
            Fluvial, Muelle Maciel, Muelle de Escala, Dársena I, Dársena II y
            Dársena Fluvial; la Rambla 25 de Agosto de 1825, Pérez Castellano,
            peatonal Sarandí, Barrio Sur, Palermo, Aguada, Capurro, Bella Vista,
            La Teja, Punta de Sayago y Villa del Cerro.
          </p>
        </div>
        <figure className="story">
          <a className="frame frame--bahia" href="/media/acta-terminal.pdf">
            <img
              src="/media/bahia.png"
              width={1100}
              height={620}
              alt="Dársenas del puerto de Montevideo en 2019"
            />
          </a>
          <figcaption>
            Dársenas, 2019. El PDF lleva Author, Producer FOP, PEM y AKIA
            sintéticos.
          </figcaption>
        </figure>
      </article>
      <section className="manifiesto">
        <h3>Papeles de la junta</h3>
        <ol>
          <li>
            <span className="kind">PDF</span>
            <a href="/media/acta-terminal.pdf">Descargar el acta</a>
          </li>
          <li>
            <span className="kind">DOCX</span>
            <a href="/media/junta.docx">Notas en Word</a>
          </li>
          <li>
            <span className="kind">ODT</span>
            <a href="/media/bitacora.odt">Bitácora de muelle</a>
          </li>
        </ol>
      </section>
    </>
  );
}
