"""
Recuperación BM25 sobre el corpus de estudio de mercado.

Por qué BM25 y no embeddings: el corpus es de ~14 documentos. Un índice
vectorial agregaría una dependencia externa, una llamada de API por
consulta y un costo recurrente para ganar poco en un corpus de este
tamaño. BM25 corre en memoria, en milisegundos, con cero costo y sin red.

Si el corpus crece por encima de ~500 documentos, reevaluar.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

K1, B = 1.5, 0.75

STOP = set("""
the a an and or but of to in on for with by from as at is are was were be been
being that this these those it its their our your we you they he she not no if
el la los las un una y o pero de del a en para con por como que se su sus es son
lo le les no si más muy solo también ya hay han ha
""".split())


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+", text) if w not in STOP and len(w) > 2]


# Un dato de ADA HPI y uno de Pearl no valen lo mismo aunque digan lo mismo.
TIER_WEIGHT = {"primary": 1.0, "reference": 0.7, "consultancy": 0.7, "vendor": 0.4}

TIER_LABEL = {
    "primary": "dato primario",
    "consultancy": "análisis de consultora — orden de magnitud",
    "vendor": "material de proveedor — señal de mercado, no evidencia",
    "reference": "referencia",
}


@dataclass
class Hit:
    score: float
    text: str
    publisher: str
    title: str
    page: int
    tier: str
    as_of: str
    caution: str
    vendor_source: bool
    quantitative: bool
    funded_study: bool

    def citation(self) -> str:
        stamp = f", {self.as_of}" if self.as_of else ""
        return f"{self.publisher}, {self.title} (p. {self.page}{stamp})"

    def usage_note(self) -> str:
        notes = [TIER_LABEL.get(self.tier, self.tier)]
        if self.caution:
            notes.append(self.caution)
        if self.funded_study:
            notes.append(
                "Estudio financiado por una aseguradora dental: usar la "
                "dirección del efecto, nunca la magnitud."
            )
        return " · ".join(notes)


class KB:
    def __init__(self, path: str | Path = "data/kb.jsonl"):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(
                f"{self.path} no existe. Corré: python -m pipeline.kb_build <carpeta>"
            )
        self.docs = [json.loads(line) for line in self.path.open()]
        self.tokens = [tokenize(d["text"]) for d in self.docs]
        self.lengths = [len(t) for t in self.tokens]
        self.avglen = sum(self.lengths) / max(1, len(self.lengths))

    @cached_property
    def _df(self) -> Counter:
        df = Counter()
        for toks in self.tokens:
            df.update(set(toks))
        return df

    def _idf(self, term: str) -> float:
        n = len(self.docs)
        df = self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def _hit(self, i: int, score: float) -> Hit:
        d = self.docs[i]
        return Hit(
            round(score, 2), d["text"], d["publisher"], d["title"], d["page"],
            d.get("tier", "vendor"), d.get("as_of", ""), d.get("caution", ""),
            d["vendor_source"], d["quantitative"], d.get("funded_study", False),
        )

    def search(
        self, query: str, k: int = 6, *,
        quantitative_only: bool = False,
        exclude_vendor: bool = False,
        max_per_source: int = 2,
    ) -> list[Hit]:
        q = tokenize(query)
        if not q:
            return []
        idf = {t: self._idf(t) for t in set(q)}

        scored: list[tuple[float, int]] = []
        for i, toks in enumerate(self.tokens):
            d = self.docs[i]
            if quantitative_only and not d["quantitative"]:
                continue
            if exclude_vendor and d["vendor_source"]:
                continue
            tf = Counter(toks)
            dl = self.lengths[i] or 1
            s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if not f:
                    continue
                s += idf[t] * (f * (K1 + 1)) / (f + K1 * (1 - B + B * dl / self.avglen))
            if s > 0:
                # El nivel de evidencia entra en el ranking, no solo en la cita.
                scored.append((s * TIER_WEIGHT.get(d.get("tier", "vendor"), 0.4), i))

        scored.sort(reverse=True)
        out, seen_pages, per_source = [], set(), Counter()
        for s, i in scored:
            d = self.docs[i]
            if (d["file"], d["page"]) in seen_pages:
                continue
            if per_source[d["file"]] >= max_per_source:
                continue          # obliga a variar fuentes en vez de citar una sola
            seen_pages.add((d["file"], d["page"]))
            per_source[d["file"]] += 1
            out.append(self._hit(i, s))
            if len(out) >= k:
                break
        return out

    def evidence_pack(self, query: str, k: int = 5) -> dict:
        """
        Lo que recibe el generador: hechos con cita, nivel de evidencia y la
        cautela de uso de cada uno.

        Regla: un pack cuya única evidencia cuantitativa sea de proveedor no
        es publicable. Serviría para sostener un claim con material de quien
        vende lo mismo que DentRead.
        """
        hits = self.search(query, k=k, quantitative_only=True)
        if len(hits) < 2:
            extra = [h for h in self.search(query, k=k) if h not in hits]
            hits = (hits + extra)[:k]
        hits = hits[:k]

        # BM25 crudo crece con el largo de la consulta: un titular con bajada
        # puntúa más que uno sin ella aunque la evidencia sea la misma. Se
        # normaliza para que el umbral signifique lo mismo en todos los casos.
        n_terms = max(1, len(set(tokenize(query))))
        top_raw = hits[0].score if hits else 0.0
        top_norm = round(top_raw / (n_terms ** 0.5), 2)

        primary = [h for h in hits if h.tier == "primary"]
        quant_primary = [h for h in primary if h.quantitative]

        return {
            "query": query,
            "top_score": top_raw,
            "top_score_norm": top_norm,
            "query_terms": n_terms,
            "facts": [{
                "text": h.text,
                "cite": h.citation(),
                "tier": h.tier,
                "usage": h.usage_note(),
            } for h in hits],
            "citations": sorted({h.citation() for h in hits}),
            "has_quantitative": any(h.quantitative for h in hits),
            "has_primary": bool(primary),
            "has_quantitative_primary": bool(quant_primary),
            "vendor_only_quantitative": (
                any(h.quantitative for h in hits) and not quant_primary
            ),
            "tier_mix": dict(Counter(h.tier for h in hits)),
        }
