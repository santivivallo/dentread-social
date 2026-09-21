# Contexto para quien trabaje en este repo

Sistema automático de contenido de **DentRead** (IA para radiografías dentales,
CEO Santiago Vivallo). Publica solo en Instagram **@dentread_** lunes, miércoles
y viernes 09:00 ET vía GitHub Actions.

Repo público: `santivivallo/dentread-social`. El README explica *qué hace*;
esto es *cómo operarlo y qué no romper*.

---

## Lo primero, si algo falla

```bash
gh run view --log-failed          # el paso exacto y su salida
```

No adivines. En la sesión donde se estabilizó esto, dos diagnósticos por
intuición fueron errados y los logs resolvieron en un intento.

---

## Las reglas que no se negocian

**1. Las cifras no las genera un modelo.** `data/facts.json` se cura a mano y
cada número se verifica contra el documento citado (`pipeline/verify.py`). Lo
que sí escribe un modelo es la **prosa que enmarca** cifras ya verificadas:
ganchos, titulares, resúmenes de noticias.

**2. Generar no consume inventario. Publicar sí.** El consumo lo marca
`publish.py` tras una publicación real. Correr `pipeline.run` para probar no
gasta nada. *Esto ya falló una vez*: cuando el consumo estaba atado a generar,
un día de pruebas quemó 5 temas, 12 hechos y 4 evergreen, el runway cayó a
cero y el cron se bloqueó solo. Si el runway baja sin explicación, comparar
`data/rotation.json` contra los `published.json` **antes** de curar nada.

**3. Los 37 cierres los aprobó Santiago uno por uno (2026-08-14).** Los 22 de
`pipeline/themes.py` y los 15 de `data/evergreen.json`. No reescribirlos sin
pedido explícito. Criterio: terminan en una implicación para quien opera la
clínica, y **nunca compiten en precisión diagnóstica** — ese es el terreno de
Pearl y Overjet, que sí tienen FDA clearance. DentRead no.

**4. Los evergreen no los escribe el modelo.** Dicen qué es DentRead; esa voz
es de la empresa.

**5. `brand/` manda.** Incluye `hook-writer.md` y `caption-writer.md`. Ojo: el
`carousel-design-system.md` de `carousel-kit Maker/` **no es de DentRead**, es
de otro proyecto. El motor es HTML → Playwright, nunca Pillow.

**6. Secretos nunca por chat ni por captura.** Van del portapapeles al `.env`
o a `gh secret set`. Se verifican por API, jamás leyendo el valor.

---

## Cómo se decide un control

La distinción que más costó aprender acá:

- **Un puntaje que ORDENA** candidatos válidos: en el peor caso elige uno
  mediocre. Va en `redaccion.puntuar`.
- **Un filtro que RECHAZA**: en el peor caso descarta contenido bueno. Va en
  `redaccion.verificar`, y solo para lo que tiene forma medible.

Dos filtros heurísticos se descartaron por esto. El detector de "titulares sin
verbo" volteaba 7 de 37 titulares correctos. **Un control con falsos positivos
altos empuja al sistema hacia contenido peor que no tener control.** Medí antes
de shipear: cada control de este repo tiene su test con casos reales.

La excepción es la exactitud: `pipeline/referentes.py` **sí rechaza**, porque
dejar pasar un desvío publica algo falso con la cita de la ADA al pie.

---

## Comandos

```bash
python -m pipeline.auditoria --peores 5   # los 26 posts, de peor a mejor
python -m pipeline.redaccion              # ¿el modelo responde?
python -m pipeline.run --slots 1          # generar (no consume)
python -m tools.preview                   # ver los slides a tamaño de feed
python -m pipeline.verify --strict        # los 4 controles
python -m tools.check_credentials         # ¿funcionan las credenciales?
gh workflow run publish.yml -f dry_run=true    # ensayo completo en CI
gh workflow run publish.yml -f dry_run=false   # publicar ahora
```

Ocho tests corren en CI antes de publicar: `test_generate`, `test_legibility`,
`test_redaccion`, `test_seleccion`, `test_referentes`, `test_archive`,
`test_fuentes_externas`, `test_llm`.

**En un clon nuevo, instalar el driver de merge del archivo de ADA**, o cada
`git pull` va a chocar en `data/ada_archive.json`: lo escriben el bot en cada
publicación y el clon local cada vez que corren los tests.

```bash
git config merge.ada-archive.driver "python3 tools/merge_archive.py %O %A %B"
```

---

## Estado al 20 de septiembre de 2026, y lo que se arregló esa semana

Esto se trabajó en una sola conversación y **no existe en ningún otro chat**.
Los commits tienen el detalle largo (`git log`); acá va lo que hay que saber
para no repetir el error.

**Publicaciones reales:** `count` 14. Salieron 4 posts en 14 días de 6
esperados. Las noticias por fin publican: 16-sep y 18-sep. Los papers siguen
en 0 pese a tener ranura del ciclo — **ese es el próximo bug a mirar**.

**Inventario:** 0 temas publicables, 5/21 hechos, stock de ADA **58** artículos
publicables del año en curso (no 155: ver el punto 10). El feed sale con la
mezcla `news 4/6 · evergreen 1/6 · paper 1/6`.

Los diez arreglos, con el error de fondo de cada uno:

1. **Las fuentes externas no quedaban registradas.**
   `mark_used_from_folder` —la única función que llama `publish.py`— hacía
   `pass` para news y paper. El que marcaba el artículo era `mark_used()`, que
   `publish.py` no llama, así que `ada_news.mark_published` nunca corrió en
   producción. La columna publicada el 16 seguía en el archivo sin marcar y
   con el puntaje más alto del stock: era el candidato uno del turno
   siguiente. Ahora `post.json` lleva `post_id` y `source_url`, se anota en
   `rotation["externos"]`, y `_un_post` descarta lo que ya salió.

2. **El archivo de ADA no se guardaba entre corridas.** No estaba en el `git
   add` del workflow. Aun con (1) arreglado, el flag se perdía igual.

3. **Una columna de opinión salió como noticia de la ADA.** *"My View: The
   future of dentistry isn't more technology"* pasó el scorer porque dice
   "technology", ×1,25 por el bucket "ai". `ada_news.es_opinion()` filtra al
   puntuar **y al leer del archivo**: el archivo reusa el score viejo para
   siempre, así que un filtro solo en `score()` no toca lo ya archivado.
   Misma lección que el `&#x2019;` publicado en un slide.

4. **Un 503 del proveedor se llevaba el post del día.** El mensaje de Gemini
   dice que es temporal y el cliente se rendía al primer intento: 0/1 posts y
   corrida en rojo. Ahora 429 y 5xx se reintentan (2, 6, 15 s), se baja de
   modelo si persiste, 401 y 404 cortan de una, y si ningún modelo responde el
   resto de la corrida usa texto curado sin volver a pagar la espera.

5. **La métrica mentía.** `semanas_de_runway` se describía como "semanas hasta
   quedarse sin contenido" y medía solo los hechos curados. Con el banco
   agotado marcaba 0,0 y **eso me hizo proponer curar cifras como urgencia de
   supervivencia**. Santiago lo cortó: el sistema se diseñó con cuatro fuentes
   justamente para no secarse. Medido: con 0 temas publicables,
   `next_posts(6)` devuelve 6 posts. La clave ahora es
   `semanas_con_posts_de_datos` y se informa `mezcla_esperada`.
   **Curar hechos recupera el balance; no evita que el sistema se detenga.**

6. **Monotonía de la grilla.** En el perfil solo se ve el frame 1, y todos
   eran oscuros. El brand guide pide *alternar*, no empezar oscuro; yo lo fijé
   y escribí un test que exigía `[oscuro, claro, oscuro]`. `spec.empieza_claro`
   alterna la polaridad entre publicaciones por contador.
   **Confirmado en el feed:** el post del 18-sep se generó con `count` en 13
   (impar) y salió con frame 1 claro; con `count` en 14 el siguiente arranca
   oscuro. La alternancia entre publicaciones funciona en producción.

7. **El camino de bloqueo del guard estaba roto.** `run_guard` leía `f.rule`,
   que `Finding` no tiene. Solo se recorre cuando un post tiene un hallazgo,
   así que el control que frena claims riesgosos fallaba justo al frenar.

Y el 20-sep, verificando si la base de contenido crecía de verdad:

8. **PubMed no tenía archivo.** BMC Oral Health y las otras nueve revistas
   están en la allowlist, pero cada corrida consultaba en vivo y descartaba en
   silencio por revista, diseño o título concluyente. Por eso el 0 de papers
   no se podía diagnosticar. `data/pubmed_archive.json` guarda cada candidato
   **con el motivo del descarte**; `python -m pipeline.journals --archivo`
   lista las revistas rechazadas más frecuentes. Los publicados se marcan.

9. **La ventana editorial tenía 2026 escrito a mano.** El 1 de enero de 2027
   el sistema habría seguido sirviendo stock de 2026 sin mirar un artículo de
   2027. Ahora `plan.anio_minimo()` se calcula; la política no cambia.
   **Al 1 de enero el stock cae a casi cero**, así que la revisión avisa en
   noviembre y diciembre: ensanchar la ventana a dos años o aceptar menos
   noticias en enero es decisión editorial.

10. **Mi métrica de stock sobrestimaba 2,7 veces.** Contaba todo el archivo
    (155) cuando el consumidor solo sirve el año en curso (**58**). Hay 382
    artículos de 2025 y 40 de 2024 que el crawl trajo y no son publicables. El
    crawl de ADA ya está en su techo (12 de 12 páginas): subirlo solo agrega
    años viejos.

El hilo común: **cada pieza hacía lo suyo bien y la falla estaba en la junta.**
Ningún control las veía porque para verlas hay que comparar corridas, no leer
una. Por eso existe la revisión quincenal.

---

## Revisión quincenal

```bash
python -m tools.revision --dias 14        # gratis, <1 s, sin llamar al modelo
```

- `data/bitacora.jsonl` (append-only) registra descartes con su motivo,
  llamadas al modelo, y **si la corrida la disparó el cron o una persona** —
  esa última es la métrica de costo real: un sistema que hay que empujar no es
  automático.
- `.github/workflows/revision.yml` corre los lunes y **se sale temprano en
  semana ISO impar** (el cron de GitHub no sabe hacer quincenal). Deja el
  informe en `informes/`, no en `docs/`, que es el sitio público.
- La tarea programada *"Revisión quincenal · DentRead Social"* lo lee y
  propone mejoras priorizadas.
- Corre con `llm.sin_modelo()`. No es solo costo: el modelo escribe distinto
  cada vez, así que un promedio medido con su texto mezclaría el estado del
  sistema con la varianza del modelo.

Jerarquía de costo del sistema, de más caro a menos: **intervención manual de
Santiago → créditos de modelo → minutos de CI** (repo público, gratis).

---

## Qué NO está cubierto

- **Si un post es interesante.** No tiene forma medible. Se intentó dos veces
  y las dos rechazaba contenido bueno. Por eso la revisión humana sigue siendo
  necesaria.
- **Desvíos de magnitud fuera de las familias conocidas** de `referentes.py`.
- **Cifra desactualizada**: falta un campo `review_by` en los hechos.
- **Los papers no publican.** Tienen 1 de 6 ranuras del ciclo y llevan 0
  publicaciones. Desde el 20-sep hay instrumento: el archivo de PubMed guarda
  el motivo de cada descarte, así que la primera corrida que toque un turno de
  paper deja el diagnóstico servido. Correr entonces
  `python -m pipeline.journals --archivo`.
- **Métricas del feed.** El sistema no lee nada de vuelta de Instagram:
  alcance, guardados ni interacciones. Mientras eso falte, "qué contenido
  funciona mejor" no es medible y cualquier propuesta al respecto es opinión.
  Se ofreció conectarlo el 19-sep y Santiago prefirió dejarlo para después.
- **LinkedIn**: la app `263015564` espera aprobación del Dev Tier de Community
  Management. Sin productos concedidos no hay OAuth posible.

---

## Cómo trabaja Santiago

Directo y crítico. Quiere **soluciones sistémicas, no parches al post que
mostró**: si te manda una captura con un defecto, arreglá la clase entera y
agregá el control que impide que vuelva. Prefiere que le digas que algo está
mal antes que un acuerdo cómodo. Si te equivocaste, decilo y arreglalo.
