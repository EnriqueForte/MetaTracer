# Visión del producto

**Proyecto:** MetaTracer  
**PRD:** [volver al índice](../PRD.md)

## Problema que resolvemos

Descubrir metadata sensible (GPS, emails, paths internos, versiones de software, comentarios de debug y similares) en documentos públicos sigue siendo **manual, lento y poco sistemático**. La información delicada permanece expuesta en sitios donde nadie la busca de forma automatizada.

Dolores habituales:

- Los hunters descargan PDFs/imágenes uno a uno e inspeccionan EXIF/propiedades del documento a mano.
- No hay un modelo de severidad consistente, así que el ruido y las fugas reales se ven igual.
- Escribir un reporte listo para bounty a partir de metadata cruda tarda más que encontrar el campo.

## Visión

Construir una herramienta de **AI-powered sensitive metadata discovery** orientada a Bug Bounty y Red Team que automatice la detección de información sensible oculta en activos públicos, clasifique el riesgo y produzca **reportes accionables**.

El ciclo de finding que el producto debe demostrar:

**descubrimiento → clasificación → reporte**

## Posicionamiento

> AI-powered sensitive metadata discovery for Bug Bounty & Red Team

Es una **herramienta de flujo OffSec autorizado**, no un scraper genérico ni un framework de exploits. Ver [ética, legal y safety](08-ethics-legal-safety.md).

## Mensaje profesional

El proyecto demuestra la capacidad de combinar:

- ingeniería de software (Python, local/Docker, SQLite con camino a Postgres)
- agentes de IA (LangGraph, control de contexto, routing de modelos)
- práctica de Seguridad Ofensiva (recon in-scope, hallazgos basados en evidencia, redacción de reportes)

## Balance del proyecto

| Proporción | Intención | Qué implica en la práctica |
| --- | --- | --- |
| **60%** | Portfolio / aprendizaje profundo | Arquitectura limpia, grafo de agentes documentado, explicaciones listas para entrevista |
| **40%** | Tool usable día a día | CLI + Web UI que usarías en un programa de bounty in-scope |

Ajustar el reparto según resultados. v1.1 (usabilidad) y v1.2 (fuentes HTML/HTTP/JS) están cerradas. La siguiente fase de producto es [v2.0 Plataforma](10-timeline-and-roadmap.md).

## Qué no es MetaTracer

- No es escaneo irrestricto de Internet.
- No sustituye suites completas de recon (subdomain enum, port scans, análisis JS profundo: sourcemaps, AST, secret scanning). v1.2 extrae comentarios de scripts in-scope, no un analizador de JavaScript.
- No es MetaHunter con otra capa de pintura: MetaHunter es la referencia de partida; MetaTracer añade agentes, clasificación, reportes, doble interfaz y safety por defecto. Ver [referencias](11-references.md).
