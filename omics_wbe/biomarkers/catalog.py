"""The biomarker catalogue: Objective 1's reference output.

A versioned, citable registry of wastewater biomarkers spanning the genomic,
proteomic and metabolomic layers, covering communicable disease, antimicrobial
resistance, non-communicable disease and chemical exposure.

Two design decisions carry most of the scientific weight:

``evidence_tier``
    ``established`` / ``emerging`` / ``prospective``. A catalogue that lists a
    prospective cancer marker beside SARS-CoV-2 N gene without saying which is
    which invites exactly the over-claiming this field exists to prevent.
    :func:`BiomarkerCatalog.inference_ready` is the gate downstream code uses.

``excretion.parameter_status``
    ``literature`` (a citable value usable as a prior) or
    ``requires_local_calibration`` (no transferable value exists). The
    back-calculation engine refuses to run on the latter unless the caller
    passes parameters explicitly, so a prevalence estimate can never be
    produced from a parameter nobody ever measured.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

CATALOG_PATH = Path(__file__).with_name("catalog.json")

OMICS_LAYERS = {"genomics", "transcriptomics", "proteomics", "metabolomics"}
DISEASE_CLASSES = {"communicable", "non_communicable", "amr", "exposure", "normaliser"}
EVIDENCE_TIERS = ("prospective", "emerging", "established")


class CatalogError(ValueError):
    """Raised when the catalogue file violates its own contract."""


class Biomarker(dict):
    """A catalogue entry. A dict subclass so it stays trivially serialisable."""

    @property
    def id(self) -> str:
        return self["biomarker_id"]

    @property
    def tier(self) -> str:
        return self["evidence_tier"]

    @property
    def is_normaliser(self) -> bool:
        return self.get("role") == "normaliser"

    def excretion_parameters(self) -> dict[str, Any] | None:
        return self.get("excretion")

    def has_literature_excretion(self) -> bool:
        exc = self.get("excretion") or {}
        return (
            exc.get("parameter_status") == "literature"
            and exc.get("excretion_fraction_of_dose") is not None
        )

    def citations(self) -> list[str]:
        return [r["citation"] for r in self.get("references", [])]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Biomarker {self['biomarker_id']} ({self['omics_layer']}/{self['evidence_tier']})>"


class BiomarkerCatalog:
    """Loaded, validated view over ``catalog.json``."""

    def __init__(self, payload: dict[str, Any]):
        self.version: str = payload["catalog_version"]
        self.tier_definitions: dict[str, str] = payload["evidence_tier_definitions"]
        self.parameter_status_definitions: dict[str, str] = payload["parameter_status_definitions"]
        self._by_id: dict[str, Biomarker] = {}
        self._by_gene_target: dict[str, str] = {}
        for raw in payload["biomarkers"]:
            self._register(Biomarker(raw))

    # -- loading ----------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path = CATALOG_PATH) -> "BiomarkerCatalog":
        return cls(json.loads(Path(path).read_text()))

    def _register(self, bm: Biomarker) -> None:
        bid = bm.get("biomarker_id")
        if not bid:
            raise CatalogError("catalogue entry without a biomarker_id")
        if bid in self._by_id:
            raise CatalogError(f"duplicate biomarker_id: {bid}")
        if bm.get("omics_layer") not in OMICS_LAYERS:
            raise CatalogError(f"{bid}: unknown omics_layer {bm.get('omics_layer')!r}")
        if bm.get("disease_class") not in DISEASE_CLASSES:
            raise CatalogError(f"{bid}: unknown disease_class {bm.get('disease_class')!r}")
        if bm.get("evidence_tier") not in EVIDENCE_TIERS:
            raise CatalogError(f"{bid}: unknown evidence_tier {bm.get('evidence_tier')!r}")
        if not bm.get("references"):
            raise CatalogError(f"{bid}: catalogue entries must carry at least one reference")
        for ref in bm["references"]:
            if not ref.get("pmid") and not ref.get("doi"):
                raise CatalogError(f"{bid}: reference without a PMID or DOI")
        exc = bm.get("excretion")
        if exc is not None and exc.get("parameter_status") not in self.parameter_status_definitions:
            raise CatalogError(f"{bid}: unknown excretion.parameter_status {exc.get('parameter_status')!r}")

        self._by_id[bid] = bm
        for gene in bm.get("nwss_gene_targets", []):
            key = _norm(gene)
            existing = self._by_gene_target.get(key)
            if existing and existing != bid:
                raise CatalogError(f"gene target {gene!r} maps to both {existing} and {bid}")
            self._by_gene_target[key] = bid

    # -- lookup -----------------------------------------------------------
    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self):
        return iter(self._by_id.values())

    def __contains__(self, biomarker_id: object) -> bool:
        return biomarker_id in self._by_id

    def get(self, biomarker_id: str) -> Biomarker:
        try:
            return self._by_id[biomarker_id]
        except KeyError:
            raise KeyError(f"unknown biomarker_id {biomarker_id!r}") from None

    def resolve_gene_target(self, gene_target: str | None) -> str | None:
        """Map a raw assay-level target string (``"n1"``, ``"InfB"``) to a biomarker_id.

        Returns ``None`` rather than guessing when the string is unrecognised;
        the ingest layer counts those and reports them instead of dropping them
        silently.
        """
        if gene_target is None:
            return None
        return self._by_gene_target.get(_norm(str(gene_target)))

    # -- selection --------------------------------------------------------
    def select(
        self,
        *,
        omics_layer: str | None = None,
        disease_class: str | Iterable[str] | None = None,
        min_tier: str | None = None,
        include_normalisers: bool = False,
    ) -> list[Biomarker]:
        if min_tier is not None and min_tier not in EVIDENCE_TIERS:
            raise ValueError(f"min_tier must be one of {EVIDENCE_TIERS}")
        floor = EVIDENCE_TIERS.index(min_tier) if min_tier else 0
        classes = (
            {disease_class} if isinstance(disease_class, str)
            else set(disease_class) if disease_class is not None
            else None
        )
        out = []
        for bm in self._by_id.values():
            if not include_normalisers and bm.is_normaliser:
                continue
            if omics_layer and bm["omics_layer"] != omics_layer:
                continue
            if classes is not None and bm["disease_class"] not in classes:
                continue
            if EVIDENCE_TIERS.index(bm["evidence_tier"]) < floor:
                continue
            out.append(bm)
        return sorted(out, key=lambda b: b["biomarker_id"])

    def inference_ready(self, biomarker_id: str) -> bool:
        """Whether this marker may back a published population-health inference.

        ``prospective`` markers never qualify: they are in the catalogue to fix
        the schema and record the open question, not to support a claim.
        """
        return self.get(biomarker_id)["evidence_tier"] in ("established", "emerging")

    # -- reporting --------------------------------------------------------
    def summary(self) -> dict[str, Any]:
        from collections import Counter
        return {
            "catalog_version": self.version,
            "n_biomarkers": len(self._by_id),
            "by_omics_layer": dict(Counter(b["omics_layer"] for b in self._by_id.values())),
            "by_disease_class": dict(Counter(b["disease_class"] for b in self._by_id.values())),
            "by_evidence_tier": dict(Counter(b["evidence_tier"] for b in self._by_id.values())),
            "n_unique_references": len({
                r.get("pmid") or r.get("doi") for b in self._by_id.values() for r in b["references"]
            }),
            "n_with_literature_excretion": sum(
                1 for b in self._by_id.values() if b.has_literature_excretion()
            ),
        }

    def to_table(self):
        """Flat pandas view, for the catalogue table published with the report."""
        import pandas as pd

        rows = []
        for b in self._by_id.values():
            exc = b.get("excretion") or {}
            rows.append({
                "biomarker_id": b["biomarker_id"],
                "name": b["name"],
                "omics_layer": b["omics_layer"],
                "disease_class": b["disease_class"],
                "conditions": "; ".join(b["conditions"]),
                "assay": b["assay"],
                "evidence_tier": b["evidence_tier"],
                "role": b.get("role", "target"),
                "preferred_normaliser": b.get("preferred_normaliser"),
                "excretion_parameter_status": exc.get("parameter_status"),
                "n_references": len(b["references"]),
                "primary_reference": b["references"][0]["citation"] if b["references"] else "",
                "caveats": " | ".join(b.get("caveats", [])),
            })
        return pd.DataFrame(rows).sort_values(["disease_class", "biomarker_id"]).reset_index(drop=True)


def _norm(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "")


@lru_cache(maxsize=1)
def default_catalog() -> BiomarkerCatalog:
    """Process-wide singleton for the shipped catalogue."""
    return BiomarkerCatalog.load()
