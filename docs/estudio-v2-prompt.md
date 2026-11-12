# Estudio v2: el redisseny de la maqueta + un editor tipus CapCut

Prompt per a una sessió llarga (goal). Copia-ho tot, a partir de «## Objectiu», com a primer missatge.

---

## Objectiu

Fer dues coses a l'Estudio (la web interna d'aquest repositori; la faig servir cada dia, sovint des del mòbil, per
gestionar ~30 canals de YouTube, i la comparteixo amb un «partner» que només veu els seus canals):

- **A. Redisseny** seguint la maqueta aprovada: https://claude.ai/artifact/9fa6W1oucoZ63YErDWxQa6 (llegeix-la amb
  l'eina Artifact, acció `read`; té tres pantalles: `Main.dc.html` Inici com a pipeline, `Canales.dc.html` salut de
  cada canal, `Video.dc.html` fitxa amb storyboard).
- **B. Editor tipus CapCut** dins de l'Estudio: canviar i retallar plans, afegir transicions, efectes, textos, música
  i SFX, i inserir els renders/composicions de Remotion que ja tenim, amb previsualització idèntica al render final.

Treballa per fases, amb un commit per fase que deixi la web funcionant, a la branca que et diguin (crea-la des de
`main` si cal). No obris PR fins que no t'ho demani.

## Com és ara (llegeix-ho abans de tocar res)

- Estudio: `pipeline/web.py` (http.server de la biblioteca estàndard) + `pipeline/web_static/` (`index.html`,
  `app.css`, `js/*.js` sense framework, rutes per hash). Peces que s'han de reaprofitar: `paint.js` (repinta comparant
  amb el DOM: no toquis l'`innerHTML` directament, fes servir `show()`/`fill()`), `ui.js` (`toast`, `ask`,
  `askText`, `sheet`: res d'`alert`/`confirm`/`prompt`), `core.js` (`icon()`, `field()`, `empty()`, `thumb()`,
  `dot()`, `lazySelect()`), i el sistema de `app.css` (variables, components, utilitats; cap `style="…"` llevat de
  valors de dades `--c`/`--v`).
- Servidor: estàtics amb versió (`?v=`), ETag/Last-Modified i 304; la pestanya es recarrega sola quan canvia
  `service.code.id`. La VPS s'actualitza sola amb `git pull` (Caddy davant, `scripts/vps/install-web.sh`).
- Editor actual: `pipeline/editor.py` (`python main.py --editor SLUG`, port 8766, només local),
  `editor/src/*.tsx` (React + `@remotion/player`, empaquetat amb esbuild a `editor/dist/app.js` quan està
  desactualitzat), `pipeline/edit_model.py` (aplica `work/<slug>/edits.json` sobre el `timeline.json`: canvis de pla,
  textos, àudio, reordenar/esborrar escenes), API `/api/state|edit|edits|apply|render|templates|assets|waveform|options`.
- Remotion: `remotion/Documentary.tsx` + `remotion/components/` (BRoll, CutMotion, FilmBurn, LowerThird, Chapter,
  Stat, graphics/* …), `remotion/types.ts` (`TimelineProps`), `remotion/lab/` (RaceReplay, RingJam, Cruces,
  SimPreview), `remotion/sim/`. Recursos a `assets/` (music, sfx, …).
- Tests: `tests/test_web.py`, `tests/test_socios.py`, `tests/test_servidor.py` i els de l'editor si n'hi ha.

## Restriccions

- Cap ruta `#/…`, endpoint ni format existent canvia; afegir-ne de nous sí. Els permisos del partner no s'amplien
  (un partner només veu i edita vídeos dels seus canals: aplica `partner_may` també a tot el que afegeixis).
  Les claus de localStorage existents continuen valent.
- L'Estudio continua sense pas de compilació (només `git pull`). L'editor és l'única excepció que ja existeix
  (esbuild); abans de decidir com s'empaqueta a la VPS, comprova si hi ha `node_modules` i Node allà (el render de
  Remotion els necessita). Si no és segur, proposa'm les opcions (bundle compilat al repo vs compilar al servidor) i
  espera la meva resposta abans de continuar la part B.
- Res de CDNs. Dependències npm noves només si són de Remotion oficials i amb la mateixa versió que la resta
  (4.0.525); cap dependència Python nova.
- Textos de la interfície en castellà i amb el mateix to; comentaris del codi en anglès.
- Tema fosc i clar, mòbil a partir de 360 px, accessible amb teclat (com ara).

## Part A: el redisseny (fases A1–A4)

1. **A1 · Carcassa comuna.** Selector de canal global a la barra lateral («Todos los canales» + canals fixats amb el
   seu color): en triar-ne un, totes les pàgines es filtren (clau nova de localStorage, p. ex. `estudio:canal`; Inici
   ja té `inicio:canal`: unifica-les respectant el valor antic). Paleta d'ordres ⌘K / Ctrl+K: anar a un vídeo, canal
   o pàgina i accions («Nuevo vídeo», «Reintentar todos», «Pausar»…), amb la cerca «¿Ya lo hice?» integrada.
2. **A2 · Inici com a pipeline.** Franja «Necesitan tu atención» amb les causes i «Reintentar los N»; quatre xifres
   (per pujar avui, buits 7 dies, YouTube 24 h, despesa); tauler Guion → Voz → En cola → Haciéndose → Para subir →
   Subidos (7 dies) amb targetes de miniatura, canal, estat i progrés; vistes Tablero / Lista (l'actual) / Solo
   Shorts. Al mòbil el tauler es converteix en seccions plegables per columna.
3. **A3 · Pàgina «Canales» (`#/canales`).** Una targeta per canal: estat, reserva, en marxa, vistes 7 dies amb
   tendència, tira de 14 dies del calendari i vistes per setmana (8). Filtres «Con huecos», «Sin reserva», «Con
   errores» i ordre «lo urgente primero». Si cal un endpoint nou (p. ex. `/api/canales`), que reaprofiti el que ja
   calculen agenda, stats i overview i vagi a `_CACHE`; amb partner, només els seus canals.
4. **A4 · Fitxa amb storyboard.** Reproductor + graella de plans (miniatura, minut, origen, frase, vora segons el
   veredicte de «Revisar»), columna amb les etapes i «Para YouTube». Botó «Editar» que obre la part B.

## Part B: l'editor (fases B1–B5)

1. **B1 · Dins de l'Estudio.** `#/editor/<slug>` servit per `web.py` amb la mateixa sessió i permisos (prefixa l'API
   de l'editor, p. ex. `/api/editor/<slug>/…`, reaprofitant les funcions d'`editor.py`). Que continuï funcionant
   `python main.py --editor SLUG`. Mateix sistema visual que l'Estudio.
2. **B2 · Línia de temps tipus CapCut.** Pistes: vídeo/imatge, gràfics i inserts, text, veu, música, SFX. Seleccionar,
   arrossegar, retallar les vores, dividir (S), esborrar, duplicar, moure entre pistes, imant (snapping), zoom de la
   línia de temps, forma d'ona, desfer/refer (Ctrl+Z / Ctrl+Shift+Z), J/K/L i espai per reproduir. Panell de
   propietats del clip seleccionat. Tot es guarda a `edits.json` (amplia l'esquema amb versió i compatibilitat cap
   enrere; `edit_model.build` l'aplica) i ha de sobreviure a refer una etapa.
3. **B3 · Transicions i efectes (a Remotion).** Transicions entre plans: tall, fosa encadenada, fosa a negre, «whip»,
   zoom, i les que ja fa `CutMotion`; durada editable. Efectes per clip: Ken Burns/zoom, velocitat, correcció de
   color (brillantor, contrast, saturació, temperatura) i uns quants «looks», desenfocament, vinyeta, grànul de
   pel·lícula / `FilmBurn`. Text: títols, rètols (`LowerThird`), xifres (`Stat`) amb els estils del canal. Ho ha de
   pintar `Documentary.tsx` igual al Player que al render.
4. **B4 · Biblioteca de renders i composicions.** Localitza els renders que ja tenim fets i les composicions
   reutilitzables (`remotion/lab`, `remotion/components/graphics`, plantilles de `/api/templates`, `assets/`, i si n'hi
   ha, carpetes de clips renderitzats; si no ho trobes clar, pregunta'm on són). Panell «Recursos» a l'editor per
   cercar-los amb miniatura i previsualització i inserir-los a la línia de temps amb les seves propietats editables;
   pujar-ne de nous.
5. **B5 · Aplicar i renderitzar.** «Aplicar» (només redescarrega el que cal) i «Renderizar» amb progrés, cua i
   avís en acabar; comparació de fotogrames Player vs render en 3 punts per assegurar que coincideixen.

L'editor és per a l'escriptori; al mòbil n'hi ha prou amb veure-ho i fer canvis simples (canviar un pla, un text).

## Com treballar

- Abans de cada fase, captures de partida (escriptori 1440 i mòbil 390, fosc i clar). Si no hi ha banc de proves a
  `tests/ui/`, crea'n un amb Playwright (Chromium ja instal·lat: `require('playwright')`) que simuli `/api/*` amb dades
  realistes: 30 canals, ~300 vídeos en tots els estats, uns quants amb error, i un vídeo complet per a l'editor.
- Després de cada fase: totes les rutes en mode propietari i partner, sense errors de consola ni desbordament
  horitzontal; auditoria d'accessibilitat (botons i camps amb nom); `python -m pytest tests/test_web.py
  tests/test_socios.py tests/test_servidor.py` (i els de l'editor); prova de no-regressió del 304 i del repintat
  (refresc amb les mateixes dades = 0 canvis al DOM).
- Part B: tests de `edit_model` per a cada operació nova (dividir, retallar, transició, efecte, insert) i per a la
  compatibilitat amb els `edits.json` antics; un render curt de prova.
- Si alguna cosa necessita una decisió meva (empaquetat de l'editor, on són els renders, dades que el servidor no té),
  pregunta i continua amb el que no en depengui.

## Què vull al final

- Taula abans/després (pes, nodes, temps de pintat de les pàgines tocades; per a l'editor, temps d'obertura i de
  resposta en arrossegar amb un vídeo de 25 min).
- Captures abans/després d'Inici, Canales, la fitxa i l'editor, en escriptori i mòbil.
- La llista clara del que no has fet o no has pogut comprovar.
