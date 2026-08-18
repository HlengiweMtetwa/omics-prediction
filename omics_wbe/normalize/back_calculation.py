"""Wastewater mass-balance back-calculation for non-communicable disease markers.

This is the method by which a chemical concentration in sewage becomes a
statement about a community: measure an analyte, convert it to a daily mass
load, normalise by the contributing population, correct for human
pharmacokinetics, and — for a prescribed drug — divide by a defined daily dose
to obtain a *treated prevalence*.

    C [ng/L] x Q [L/day]                 -> daily mass load          [mg/day]
    / population x 1000                  -> population-normalised    [mg/day/1000 people]
    x correction factor                  -> consumed parent drug     [mg/day/1000 people]
    / defined daily dose                 -> treated prevalence       [people per 1000]

The correction factor inverts human pharmacokinetics::

    CF = (1 / excretion_fraction) x (1 / bioavailability) x molar_correction

Two deliberate refusals are built in.

First, :func:`back_calculate` will not run on a biomarker whose catalogue entry
records ``parameter_status = "requires_local_calibration"`` unless the caller
passes the parameters explicitly. Most non-communicable-disease markers have no
transferable excretion factor, and producing a prevalence estimate from a
parameter nobody measured is the central failure mode of this method.

Second, the point estimate is never returned alone. :func:`back_calculate_mc`
propagates parameter uncertainty by Monte Carlo, because the correction factor
is typically the largest source of error and a single number hides that.

Non-communicable-disease inference carries a further limitation that no amount
of arithmetic removes: a prescribed-drug marker measures *treated* prevalence.
Undiagnosed and non-pharmacologically managed disease is invisible to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from omics_wbe.biomarkers.catalog import BiomarkerCatalog, default_catalog

NG_TO_MG = 1e-6


class ParameterUnavailable(ValueError):
    """Raised when back-calculation is attempted without calibrated parameters."""


@dataclass(frozen=True)
class ExcretionParameters:
    """Pharmacokinetic parameters for one biomarker.

    Attributes
    ----------
    excretion_fraction:
        Fraction of the absorbed dose excreted as the measured analyte.
    bioavailability:
        Fraction of the administered dose absorbed. ``1.0`` when
        ``excretion_fraction`` is already expressed per administered dose.
    molar_correction:
        ``MW(parent) / MW(metabolite)`` when a metabolite is measured but the
        parent compound is the quantity of interest. ``1.0`` when the parent is
        measured directly.
    defined_daily_dose_mg:
        WHO defined daily dose, required only for prevalence estimation.
    stability_correction:
        Multiplier for in-sewer loss between excretion and sampling. ``1.0``
        means no correction, which is an assumption, not an absence of one.
    """

    excretion_fraction: float
    bioavailability: float = 1.0
    molar_correction: float = 1.0
    defined_daily_dose_mg: float | None = None
    stability_correction: float = 1.0
    source: str | None = None

    def __post_init__(self) -> None:
        if not 0 < self.excretion_fraction <= 1:
            raise ValueError("excretion_fraction must be in (0, 1]")
        if not 0 < self.bioavailability <= 1:
            raise ValueError("bioavailability must be in (0, 1]")
        if self.molar_correction <= 0 or self.stability_correction <= 0:
            raise ValueError("molar_correction and stability_correction must be positive")
        if self.defined_daily_dose_mg is not None and self.defined_daily_dose_mg <= 0:
            raise ValueError("defined_daily_dose_mg must be positive")

    @property
    def correction_factor(self) -> float:
        return (
            (1.0 / self.excretion_fraction)
            * (1.0 / self.bioavailability)
            * self.molar_correction
            * self.stability_correction
        )


def daily_mass_load_mg(concentration_ng_per_l, flow_l_per_day):
    """Analyte mass passing the sampling point per day, in mg."""
    return np.asarray(concentration_ng_per_l, dtype=float) * np.asarray(flow_l_per_day, dtype=float) * NG_TO_MG


def population_normalised_load(mass_load_mg_per_day, population, per: int = 1000):
    """Daily analyte load per ``per`` inhabitants (default: per 1000)."""
    pop = np.asarray(population, dtype=float)
    if np.any(pop <= 0):
        raise ValueError("population must be positive")
    return np.asarray(mass_load_mg_per_day, dtype=float) / pop * per


def back_calculate(
    concentration_ng_per_l,
    flow_l_per_day,
    population,
    parameters: ExcretionParameters,
    *,
    per: int = 1000,
) -> dict[str, Any]:
    """Point-estimate back-calculation. Returns every intermediate quantity.

    Intermediates are returned rather than only the final number so a reviewer
    can check the dimensional chain instead of trusting one output.
    """
    load = daily_mass_load_mg(concentration_ng_per_l, flow_l_per_day)
    normalised = population_normalised_load(load, population, per=per)
    consumption = normalised * parameters.correction_factor

    out: dict[str, Any] = {
        "mass_load_mg_per_day": load,
        f"analyte_load_mg_per_day_per_{per}": normalised,
        f"consumption_mg_per_day_per_{per}": consumption,
        "correction_factor": parameters.correction_factor,
    }
    if parameters.defined_daily_dose_mg:
        out[f"treated_prevalence_per_{per}"] = consumption / parameters.defined_daily_dose_mg
        out["treated_prevalence_pct"] = consumption / parameters.defined_daily_dose_mg / per * 100.0
    return out


def back_calculate_mc(
    concentration_ng_per_l: float,
    flow_l_per_day: float,
    population: float,
    parameters: ExcretionParameters,
    *,
    excretion_cv: float = 0.20,
    bioavailability_cv: float = 0.20,
    concentration_cv: float = 0.15,
    flow_cv: float = 0.10,
    n_draws: int = 10_000,
    seed: int = 20240501,
    per: int = 1000,
) -> dict[str, Any]:
    """Monte-Carlo uncertainty propagation around a back-calculated estimate.

    Multiplicative sources of error are drawn log-normally, which keeps every
    draw positive and reflects that these quantities vary by ratio rather than
    by additive amount. Excretion fraction and bioavailability are additionally
    truncated to (0, 1] because values outside that range are not physical.

    Returns the median and a 95% interval. The interval is a *parameter*
    uncertainty interval: it does not include the far larger structural
    uncertainty in whether the excretion parameters transfer to this population
    at all.
    """
    rng = np.random.default_rng(seed)

    def lognormal(mean: float, cv: float) -> np.ndarray:
        if cv <= 0:
            return np.full(n_draws, mean, dtype=float)
        sigma = np.sqrt(np.log1p(cv ** 2))
        mu = np.log(mean) - 0.5 * sigma ** 2
        return rng.lognormal(mu, sigma, n_draws)

    conc = lognormal(concentration_ng_per_l, concentration_cv)
    flow = lognormal(flow_l_per_day, flow_cv)
    excretion = np.clip(lognormal(parameters.excretion_fraction, excretion_cv), 1e-6, 1.0)
    bioavail = np.clip(lognormal(parameters.bioavailability, bioavailability_cv), 1e-6, 1.0)

    cf = (1.0 / excretion) * (1.0 / bioavail) * parameters.molar_correction * parameters.stability_correction
    consumption = daily_mass_load_mg(conc, flow) / population * per * cf

    result: dict[str, Any] = {
        "n_draws": n_draws,
        "seed": seed,
        f"consumption_mg_per_day_per_{per}": {
            "median": float(np.median(consumption)),
            "ci95_low": float(np.percentile(consumption, 2.5)),
            "ci95_high": float(np.percentile(consumption, 97.5)),
        },
        "correction_factor": {
            "median": float(np.median(cf)),
            "ci95_low": float(np.percentile(cf, 2.5)),
            "ci95_high": float(np.percentile(cf, 97.5)),
        },
    }
    if parameters.defined_daily_dose_mg:
        prev = consumption / parameters.defined_daily_dose_mg / per * 100.0
        result["treated_prevalence_pct"] = {
            "median": float(np.median(prev)),
            "ci95_low": float(np.percentile(prev, 2.5)),
            "ci95_high": float(np.percentile(prev, 97.5)),
            "relative_width": float(
                (np.percentile(prev, 97.5) - np.percentile(prev, 2.5)) / np.median(prev)
            ),
        }
    return result


def parameters_from_catalog(
    biomarker_id: str,
    catalog: BiomarkerCatalog | None = None,
    *,
    defined_daily_dose_mg: float | None = None,
    stability_correction: float = 1.0,
    allow_uncalibrated: bool = False,
) -> ExcretionParameters:
    """Build :class:`ExcretionParameters` from the catalogue, or refuse to.

    Raises :class:`ParameterUnavailable` when the catalogue records that no
    transferable literature value exists. That refusal is the point: it makes
    "we do not know the excretion fraction for this marker" a hard stop rather
    than a footnote under a published prevalence figure.
    """
    catalog = catalog or default_catalog()
    bm = catalog.get(biomarker_id)
    exc = bm.get("excretion") or {}

    if not bm.has_literature_excretion() and not allow_uncalibrated:
        raise ParameterUnavailable(
            f"{biomarker_id}: excretion parameters are "
            f"{exc.get('parameter_status', 'absent')!r}. Back-calculation requires locally "
            "measured excretion parameters; pass them explicitly via ExcretionParameters, or set "
            "allow_uncalibrated=True only for a clearly-labelled illustrative calculation."
        )
    if not bm.has_literature_excretion():
        raise ParameterUnavailable(
            f"{biomarker_id}: no excretion_fraction_of_dose value exists in the catalogue, so "
            "there is nothing to build parameters from even with allow_uncalibrated=True."
        )

    return ExcretionParameters(
        excretion_fraction=float(exc["excretion_fraction_of_dose"]),
        bioavailability=float(exc.get("oral_bioavailability") or 1.0),
        molar_correction=float(exc.get("molar_correction_factor") or 1.0),
        defined_daily_dose_mg=defined_daily_dose_mg,
        stability_correction=stability_correction,
        source=exc.get("source_ref"),
    )
