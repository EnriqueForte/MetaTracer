# Spec 54 — Host público del lab Puertomontevideo

**Estado:** active  
**Agente previsto:** lab (no `v2-ui-engineer`) · docs: `docs-architect`  
**Task:** [.aicontext/tasks/54-lab-host.md](../.aicontext/tasks/54-lab-host.md)

## Intención

Publicar el semanario sintético de spec 53 en un host **HTTPS gratuito** para
que MetaTracer pueda crawlearlo (loopback sigue bloqueado). No es producto.

## Alcance (cerrado)

- Paquete estático = `npm run build` de `lab/puertomontevideo` (HTML prerenderizado + media).
- Cabeceras de recon vía `_headers` / `netlify.toml` (allowlist HTTP de TASK-00).
- Host: Cloudflare Pages o Netlify (plan free). Banner de laboratorio intacto.
- Documentar la URL y el `--scope-domain` en el README del lab.

## Fuera de alcance

`src/` y `web/`. Bypass de loopback. Dominio de pago. Impersonar ANP/IMM.
Indexación como medio real. Secrets reales.
