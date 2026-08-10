# Política de claims — DentRead

El error que corrige esta política: aplicar el lenguaje más restrictivo a
toda comunicación. Eso protegía de un claim falso y a la vez impedía decir
lo que DentRead es.

**DentRead es una empresa de inteligencia artificial aplicada a radiografías
dentales y al flujo clínico.** Esa frase es descripción, no promesa, y debe
poder decirse sin rodeos.

---

## 1. Cinco tipos de comunicación, cinco niveles de exigencia

| Tipo | Qué es | Exigencia | Ejemplo |
|---|---|---|---|
| **Posicionamiento corporativo** | Qué es la empresa y hacia dónde va | Que sea verdad hoy | "DentRead desarrolla herramientas de IA para radiografías dentales y flujos clínicos." |
| **Descripción técnica** | Qué hace el producto | Que la función exista | "El sistema procesa radiografías y organiza la información." |
| **Claim comercial** | Qué gana el cliente | Matiz o evidencia | "Puede contribuir a una evaluación más consistente." |
| **Claim clínico** | Efecto sobre diagnóstico, tratamiento o salud | Evidencia publicada | Requiere estudio. Sin él, no se hace. |
| **Claim regulatorio** | Estado ante una autoridad | Documento emitido | "FDA-cleared" solo con número y fecha. |

Los dos primeros no necesitan matiz. Confundirlos con los tres últimos es lo
que empobrecía el lenguaje.

---

## 2. El modelo del guard: dominio × fuerza

`publisher/guard.py` clasifica cada afirmación en dos ejes y decide por la
combinación, no por la palabra.

### Dominio

| Dominio | Qué afirma |
|---|---|
| `capability` | Qué hace el producto |
| `performance` | Qué tan bien lo hace (sensibilidad, precisión) |
| `outcome` | Qué consigue el usuario (aceptación, tiempo, ingresos) |
| `quantified_outcome` | Lo anterior, con cifra |
| `regulatory` | Estado ante FDA, CE, HIPAA, ISP |
| `comparative` | Comparación con competidor nombrado |
| `traction` | Clientes, pilotos, volumen |
| `replacement` | Sustitución del profesional |
| `guarantee` | Promesa absoluta, sobre cualquier cosa |
| `phi` | Identificadores de paciente |

### Fuerza

| Fuerza | Marcadores |
|---|---|
| `hedged` | busca, puede, está diseñado para, apunta a, contribuye a |
| `assertive` | mejora, reduce, aumenta, acelera |
| `absolute` | garantiza, elimina, siempre, 100%, cero errores |

### Matriz de decisión

| Dominio | hedged | assertive | absolute |
|---|---|---|---|
| capability | libre | libre | BLOCK |
| outcome | libre | REVIEW | BLOCK |
| performance | REVIEW | REVIEW | BLOCK |
| quantified_outcome | REVIEW | REVIEW | BLOCK |
| regulatory | REVIEW | REVIEW | BLOCK |
| comparative | REVIEW | BLOCK | BLOCK |
| traction | REVIEW | REVIEW | BLOCK |
| replacement | REVIEW | BLOCK | BLOCK |
| guarantee | BLOCK | BLOCK | BLOCK |
| phi | BLOCK | BLOCK | BLOCK |

Un `REVIEW` se satisface declarando la evidencia en `post.json`:
`has_source`, `model_metrics_documented`, `regulatory_status_verified`,
`traction_verified`, `head_to_head_study`.

### Negación

Un término regulado negado dice lo contrario del claim. "No reemplaza al
profesional" se detecta por contexto y no bloquea. Es una frase que DentRead
debe poder usar cuando el contexto lo pide — pero ya no está obligada a
usarla en cada publicación.

---

## 3. Qué quedó libre

Estas expresiones se evaluaban antes como riesgo y ahora pasan:

- "IA para radiografías dentales"
- "Apoyo al análisis radiográfico"
- "Apoyo a la toma de decisiones clínicas"
- "Mejorar el desempeño del dentista" *(dentro de un objetivo de diseño)*
- "Facilitar la comunicación con pacientes"
- "Apoyar la aceptación de tratamientos"
- "Mejorar la comprensión y confianza del paciente"

Verificado: 14 formulaciones legítimas pasan, 10 riesgosas se bloquean, cero
errores en ambas direcciones.

---

## 4. Qué sigue bloqueado, y por qué

| Bloqueado | Motivo |
|---|---|
| "garantiza menos errores" | Una garantía es una obligación creada en un post |
| "92% de sensibilidad" | Exige dataset, N, población y método |
| "aumenta la aceptación un 37%" | Resultado atribuido al producto sin medición |
| "FDA-cleared" | Se verifica en un registro público en un clic |
| "más preciso que Pearl" | Publicidad comparativa sin estudio head-to-head |
| "200 clínicas confían" | Se verifica en una llamada |
| "reemplaza al radiólogo" | Agrava el perfil regulatorio en cualquier jurisdicción |

---

## 5. Contexto: no todo se revisa igual

El nivel de revisión debería depender de estas variables. Hoy el código
aplica la matriz completa a todo; los ejes de país y canal quedan
documentados para cuando haya material segmentado.

| Variable | Efecto |
|---|---|
| **País** | EE.UU. exige más cuidado con claims de desempeño diagnóstico. Chile y LatAm tienen otro marco. Un mismo mensaje puede requerir matiz distinto |
| **Audiencia** | A un profesional se le puede hablar con precisión técnica; a un paciente hay que evitar que infiera una promesa clínica |
| **Canal** | Una página indexada es permanente; un carrusel desaparece. La página exige más rigor |
| **Producto** | Cada herramienta tiene su propio uso previsto |
| **Uso previsto** | Es lo que define el estatus regulatorio, más que la tecnología |
| **Fuerza** | Ya implementada en la matriz |
| **Evidencia** | Ya implementada vía declaraciones |

**Regla práctica:** el uso previsto declarado es lo que determina si algo cae
bajo regulación de dispositivo médico. Describir capacidades no lo activa;
afirmar desempeño diagnóstico sí.

---

## 6. Fuentes

`data/sources.json`. La autorización depende del tier de la fuente y del tipo
de claim que se quiere sostener, no de una lista fija.

| Tier | Puede sostener |
|---|---|
| `regulatory` | regulatorio, capacidad, contexto |
| `primary_research` | desempeño, resultado, contexto, capacidad |
| `institutional_data` | contexto, resultado |
| `professional_body` | contexto, capacidad, regulatorio |
| `academic` | contexto, desempeño, capacidad |
| `consultancy` | contexto — orden de magnitud |
| `trade_press` | contexto — verificar contra la primaria |
| `vendor` | contexto — señal de mercado, con el proveedor a la vista |
| `dentread_internal` | desempeño, resultado, capacidad — declarando método |

Agregar una fuente es una entrada en el JSON. **Ningún tier habilita
cualquier claim**: una consultora no sostiene una métrica de desempeño por
más prestigiosa que sea.

---

## 7. Cómo actualizar el posicionamiento sin tocar código

1. **Cambiar cómo se describe DentRead** → editar `approved_messages` en
   `data/evergreen.json`. El generador rota entre ellos.
2. **Habilitar una expresión hoy bloqueada** → mover el patrón de dominio o
   cambiar su celda en la matriz de `guard.py`.
3. **Agregar una audiencia** → `allowed_audiences` en el bloque.
4. **Agregar un tema** → un bloque nuevo en `evergreen.json`.
5. **Agregar una fuente** → una entrada en `sources.json`.
6. **Declarar evidencia nueva** → el flag correspondiente en `post.json`.

Ninguna de las seis exige tocar la lógica del pipeline.

---

## 8. Revisión

Cada bloque tiene `review_cycle_days`, por defecto 90. `uso-responsable-ia`
está en 60 por ser el más sensible al cambio regulatorio.

Un mensaje aprobado hoy puede dejar de ser exacto cuando cambie el producto o
el estado regulatorio. **El código no puede detectarlo.**
