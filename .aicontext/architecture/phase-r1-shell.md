# R1 — shell

**Fecha:** 2026-09-29
**Estado:** Cerrada. Solo `web/`. Las plantillas de V1 no se tocaron.

El riel marca la ruta activa con una franja de `--mt-accent` y el texto en acero. Ya no hay un bloque de fondo en el ítem activo ni en el hover. History sigue activa dentro de `/runs/{id}`. Reconnaissance solo coincide con `/`.

La barra superior mide 40px: el aviso ético va en una línea que se recorta, la campana y la sesión quedan en la misma fila. El pie pasivo y el enlace Classic UI (`href="/"`) siguen. La frase de que el sign out cierra también la sesión clásica sigue en el DOM.

El título del panel de notificaciones pasa a caja de frase, sin mayúsculas espaciadas. El resto de pantallas no entra en esta fase.

Vitest del shell: frase de sign out, `href="/"` del enlace clásico, `aria-current` en Dashboard y en History con un run abierto.
