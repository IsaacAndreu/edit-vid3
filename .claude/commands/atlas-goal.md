---
description: Construye el sistema Atlas siguiendo prompts/atlas-plan.md, fase a fase
argument-hint: "[número de fase | vacío = siguiente pendiente]"
---

Objetivo: que este repositorio produzca vídeos de estilo Atlas tal como lo describe
`prompts/atlas-plan.md`.

1. Lee `CLAUDE.md`, `prompts/atlas-plan.md`, `prompts/atlas-master-prompt.md` y
   `prompts/atlas-progress.md`.
2. Fase a ejecutar: `$ARGUMENTS`. Si está vacío, la primera fase que en
   `prompts/atlas-progress.md` no figure como completada.
3. Ejecuta esa fase completa: bucle visual, criterios de aceptación, `npm run typecheck`,
   commit y push a la rama de trabajo.
4. Actualiza `prompts/atlas-progress.md` (estado, criterios cumplidos/no cumplidos,
   desviaciones del plan, fotogramas generados) y termina con el informe de la regla 7.
5. Si quedan fases y no hay una puerta de decisión pendiente (fin de la fase 3), continúa con
   la siguiente en esta misma sesión mientras el contexto lo permita. En una puerta, para y
   enseña al usuario las parejas original/render que pide el plan.
