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

Seis tests corren en CI antes de publicar: `test_generate`, `test_legibility`,
`test_redaccion`, `test_seleccion`, `test_referentes`, `test_archive`.

---

## Qué NO está cubierto

- **Si un post es interesante.** No tiene forma medible. Se intentó dos veces
  y las dos rechazaba contenido bueno. Por eso la revisión humana sigue siendo
  necesaria.
- **Desvíos de magnitud fuera de las familias conocidas** de `referentes.py`.
- **Cifra desactualizada**: falta un campo `review_by` en los hechos.
- **LinkedIn**: la app `263015564` espera aprobación del Dev Tier de Community
  Management. Sin productos concedidos no hay OAuth posible.

---

## Cómo trabaja Santiago

Directo y crítico. Quiere **soluciones sistémicas, no parches al post que
mostró**: si te manda una captura con un defecto, arreglá la clase entera y
agregá el control que impide que vuelva. Prefiere que le digas que algo está
mal antes que un acuerdo cómodo. Si te equivocaste, decilo y arreglalo.
