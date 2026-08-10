# Diferido — fuera del MVP a propósito

Estos módulos funcionan y están probados. Salieron del camino de publicación
porque agregaban complejidad sin valor proporcional en esta etapa, no porque
estuvieran rotos.

| Módulo | Qué hace | Cuándo traerlo de vuelta |
|---|---|---|
| `ada_news.py` | Ingesta de ADA News con archivo acumulativo y profundidad progresiva | Cuando el modo `data` esté saturado: 60+ hechos curados y el catálogo sin huecos. Antes de eso, comentar la agenda ajena resta |
| `newsguard.py` | Copyright, marca ADA, originalidad, atribución | Junto con `ada_news`. Solo tiene sentido con contenido derivado de terceros |
| `compose_multimodo.py` | Los tres modos de brief (`data`, `news`, `dentread`) + contexto de industria + reglas de citación | El contexto de industria y las reglas de citación sirven el día que haya un LLM redactando. Sin LLM, son texto que nadie lee |

## Por qué salieron

El MVP publica dos posts por semana desde hechos curados a mano. En ese
escenario:

- **ADA News** aportaba como mucho 1 post de cada 2, era el de menor valor
  (comentario sobre la agenda de otro) y arrastraba toda la superficie de
  copyright y atribución.
- **`newsguard`** son 196 líneas que solo se ejecutan en modo `news`.
- **Los tres modos** eran uno en uso, uno marginal y uno nunca ejecutado.

## Cómo reactivarlos

1. Mover `ada_news.py` a `pipeline/` y `newsguard.py` a `publisher/`.
2. Recuperar de `compose_multimodo.py` las funciones `build_brief_from_news`
   y los `SLIDE_PLANS["news"]`.
3. Volver a cablear `run.py` para que `plan_week` acepte noticias.
4. Correr `python -m tests.test_archive` para confirmar que el archivo
   acumulativo sigue creciendo.

Nada de esto está roto. Está esperando.
