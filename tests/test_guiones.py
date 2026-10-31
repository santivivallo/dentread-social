"""Sin red ni modelo: el filtro de cifras y la estructura de guiones/ultimo.json."""
from tools import guiones as g

HS = [{"id": "sin-seguro-72m", "number": "72 millones", "statement": "Cerca de 72 millones de adultos en EE.UU. no tienen cobertura dental.", "cite": "x"}]
F = [{"tipo": "competidor", "titulo": "Overjet raises $53M", "url": "https://n/1", "fecha": "2026-10-30"}]
base = {"titulo": "t", "formato": "Titular con dato", "gancho": "72 millones sin cobertura", "escenas": ["a", "b", "c"], "cierre": "Sigue a DentRead", "fuente_url": "", "hechos": ["sin-seguro-72m"]}

assert g.valido(base, F, HS) == (True, "")
inventado = {**base, "escenas": ["el 40% de los dentistas usa IA", "b", "c"]}
assert g.valido(inventado, F, HS)[0] is False, "cifra sin respaldo debe descartarse"
de_fuente = {**base, "hechos": [], "gancho": "Overjet levantó 53M", "fuente_url": "https://n/1"}
assert g.valido(de_fuente, F, HS) == (True, "")
assert g.valido({**base, "escenas": ["a"]}, F, HS)[0] is False
md = g.markdown({"fecha": "2026-10-31", "fuentes": 1, "guiones": [base], "descartados": [{"titulo": "x", "motivo": "cifras sin respaldo: 40"}]})
assert "Gancho (0-2 s)" in md and "Descartados" in md
r = g.generar(con_red=False)  # sin LLM_API_KEY: 0 guiones, sin romperse
assert r["guiones"] == [] and r["fuentes"] >= 0
print("guiones: filtro de cifras, fuente, estructura y corrida sin modelo OK")
