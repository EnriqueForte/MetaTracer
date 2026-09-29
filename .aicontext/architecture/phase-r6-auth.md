# R6 — auth

**Fecha:** 2026-09-29
**Estado:** Cerrada. Solo `web/`. Las plantillas de V1 no se tocaron.

Login, registro y setup usan el mismo marco: fondo `--mt-bg`, tipo del shell y un solo panel `.mt-auth-panel`. No hay riel, ni campana, ni lista de producto.

Los textos y el POST no cambian. El login sigue redirigiendo si ya hay sesión. El registro sigue oculto cuando la auth está apagada. El setup sigue pidiendo el token del log.

Vitest: las tres pantallas tienen un panel y ningún nav Primary.
