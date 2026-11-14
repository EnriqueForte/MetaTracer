export function FotogaleriaPage() {
  return (
    <section className="gallery">
      <figure className="span-2">
        <div className="frame frame--wide">
          <img
            src="/media/rambla.jpg"
            width={1200}
            height={675}
            alt="Puerto de Montevideo desde Ciudad Vieja"
          />
        </div>
        <figcaption>
          Rambla 25 de Agosto de 1825. Foto Wikimedia Commons (CC BY 2.0). IPTC
          de la mesa.
        </figcaption>
      </figure>
      <figure>
        <div className="frame frame--bahia">
          <img
            src="/media/bahia.png"
            width={1100}
            height={620}
            alt="Dársenas del puerto"
          />
        </div>
        <figcaption>
          Dársenas, 2019 (Marinna, CC BY-SA 4.0). XMP con GPS y URI de staging.
        </figcaption>
      </figure>
      <figure>
        <div className="frame frame--mercado">
          <img
            src="/media/mercado.webp"
            width={1000}
            height={560}
            alt="Mercado del Puerto en Pérez Castellano"
          />
        </div>
        <figcaption>
          Mercado del Puerto, Pérez Castellano (Felipe Restrepo Acosta, CC
          BY-SA 4.0).
        </figcaption>
      </figure>
      <figure className="span-2">
        <div className="frame frame--gif">
          <img
            src="/media/marea.gif"
            width={640}
            height={360}
            alt="Recorte animado del puerto aéreo"
          />
        </div>
        <figcaption>
          Recortes del aéreo de Fedaro. Comentario GIF de debug.
        </figcaption>
      </figure>
    </section>
  );
}
