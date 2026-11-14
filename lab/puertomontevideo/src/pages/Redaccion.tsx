const LUGARES = [
  "Ciudad Vieja",
  "Rambla 25 de Agosto",
  "Pérez Castellano",
  "peatonal Sarandí",
  "Muelle Maciel",
  "Muelle Fluvial",
  "TCP muelle C",
  "Montecon",
  "Capurro",
  "La Teja",
  "Aguada",
  "Villa del Cerro",
];

export function RedaccionPage() {
  return (
    <article className="prose">
      <h2>Mesa del Muelle</h2>
      <p>
        Redacción ficticia en Ciudad Vieja, a dos cuadras de la Rambla 25 de
        Agosto de 1825. Los cargos son inventados. No hay nombres de
        periodistas reales.
      </p>
      <div className="staff">
        <span>Secretaría de edición, cargo inventado</span>
        <span>Fotografía de puerto, cargo inventado</span>
        <a href="mailto:redaccion@puertomontevideo.press">
          redaccion@puertomontevideo.press
        </a>
      </div>
      <p>Lugares que nombra esta edición (toponimia real, relato inventado):</p>
      <ul className="lugares">
        {LUGARES.map((lugar) => (
          <li key={lugar}>{lugar}</li>
        ))}
      </ul>
      <p>
        Fotos de archivo: Wikimedia Commons. Lista en el{" "}
        <a href="https://commons.wikimedia.org/">repositorio Commons</a>;
        detalle local en CREDITS.md del lab.
      </p>
      <p className="mark">
        <img
          src="/media/marca.svg"
          width={240}
          height={64}
          alt="Marca Puertomontevideo"
        />
      </p>
    </article>
  );
}
