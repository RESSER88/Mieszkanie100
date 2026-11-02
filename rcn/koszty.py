#!/usr/bin/env python3
"""Purchase costs of a flat: one-off fees, the mortgage payment and monthly charges. Pure arithmetic.

Rates as of 2026-11 (to be checked against current law before relying on them):
- PCC 2% of the price, secondary market only (a developer's sale carries VAT inside the price);
- notary fee: maximum rates of the Minister of Justice regulation on maximum notary fees (§ 3), plus 23% VAT;
  on the primary market the maximum is half the rate, for two acts (developer agreement and transfer of ownership);
- court fees: entry of ownership 200 zł, new land register (primary market) 100 zł, mortgage entry 200 zł
  plus 19 zł PCC on the mortgage; land-register application drafted by the notary 200 zł + VAT; copies (assumed);
- agent's commission and finishing cost are the user's assumptions.
Every number is shown with its assumption on the page; this is an estimate, not an offer from a notary or a bank.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

VAT = 0.23
PCC_SECONDARY = 0.02
OWNERSHIP_ENTRY = 200.0
NEW_REGISTER = 100.0
MORTGAGE_ENTRY = 200.0
MORTGAGE_PCC = 19.0
REGISTER_APPLICATION = 200.0       # notary's fee for the land-register application, net


def notary_max(value: float) -> float:
    """Maximum notary fee (net) for a sale of the given value."""
    brackets = ((3000, 0, 100, 0.0), (10000, 3000, 100, 0.03), (30000, 10000, 310, 0.02), (60000, 30000, 710, 0.01),
                (1000000, 60000, 1010, 0.004), (2000000, 1000000, 4770, 0.002))
    for top, base, fee, rate in brackets:
        if value <= top:
            return fee + rate * (value - base)
    return min(6770 + 0.0025 * (value - 2000000), 10000)


@dataclass
class Assumptions:
    wklad_proc: float = 20.0          # own contribution, % of the price (100 = cash)
    oprocentowanie: float = 7.0       # mortgage rate, % a year
    lata: int = 25
    prowizja_proc: float = 0.0        # agent's commission, % of the price, net
    wykonczenie_m2: float = 0.0       # finishing, zł per m²
    czynsz_m2: float = 0.0            # monthly charges, zł per m²
    udzial_taksy: Optional[float] = None    # share of the maximum notary fee; None: 1 (secondary) or 0.5 (primary)
    wypisy: float = 400.0             # copies of the deed, gross


def assumptions_from(params: Dict[str, str]) -> Assumptions:
    """Read assumptions from request parameters; ValueError with a readable message on bad input."""
    def number(key, default, low, high):
        text = (params.get(key) or "").strip().replace(",", ".")
        if not text:
            return default
        try:
            value = float(text)
        except ValueError:
            raise ValueError("„%s” nie jest liczbą" % key)
        if not low <= value <= high:
            raise ValueError("„%s” poza zakresem %g–%g" % (key, low, high))
        return value
    a = Assumptions()
    return Assumptions(wklad_proc=number("wklad_proc", a.wklad_proc, 0, 100),
                       oprocentowanie=number("oprocentowanie", a.oprocentowanie, 0, 30),
                       lata=int(number("lata", a.lata, 1, 40)),
                       prowizja_proc=number("prowizja_proc", 0.0, 0, 10),
                       wykonczenie_m2=number("wykonczenie_m2", 0.0, 0, 20000),
                       czynsz_m2=number("czynsz_m2", 0.0, 0, 100),
                       udzial_taksy=number("udzial_taksy", None, 0, 1) if params.get("udzial_taksy") else None,
                       wypisy=number("wypisy", a.wypisy, 0, 5000))


def _item(key: str, label: str, amount: float, note: str) -> Dict[str, Any]:
    return {"klucz": key, "opis": label, "kwota": round(amount, 2), "uwaga": note}


def monthly_payment(principal: float, rate_pct: float, years: int) -> float:
    n = years * 12
    r = rate_pct / 100 / 12
    return principal / n if r == 0 else principal * r / (1 - (1 + r) ** -n)


def costs(price: float, area: Optional[float], market: str, a: Optional[Assumptions] = None) -> Dict[str, Any]:
    """One-off costs, the mortgage and monthly charges for a flat bought at `price` on `market` (wtorny|pierwotny)."""
    a = a or Assumptions()
    primary = market == "pierwotny"
    items: List[Dict[str, Any]] = []
    if not primary:
        items.append(_item("pcc", "Podatek PCC 2%", PCC_SECONDARY * price, "tylko rynek wtórny"))
    share = a.udzial_taksy if a.udzial_taksy is not None else (0.5 if primary else 1.0)
    acts = 2 if primary else 1
    items.append(_item("taksa", "Taksa notarialna z VAT", acts * share * notary_max(price) * (1 + VAT),
                       "%s stawki maksymalnej%s" % ("%g%%" % (share * 100), ", dwie umowy (deweloperska i przenosząca)"
                                                    if primary else "")))
    items.append(_item("wniosek_kw", "Wniosek do księgi wieczystej (notariusz)", REGISTER_APPLICATION * (1 + VAT), "z VAT"))
    items.append(_item("wypisy", "Wypisy aktu", a.wypisy, "założenie"))
    items.append(_item("wpis_wlasnosci", "Wpis własności do księgi wieczystej", OWNERSHIP_ENTRY, "opłata sądowa"))
    if primary:
        items.append(_item("zalozenie_kw", "Założenie księgi wieczystej", NEW_REGISTER, "opłata sądowa"))
    loan = price * (1 - a.wklad_proc / 100)
    if loan > 0:
        items.append(_item("hipoteka", "Wpis hipoteki z PCC", MORTGAGE_ENTRY + MORTGAGE_PCC, "200 zł opłaty sądowej + 19 zł PCC"))
    if a.prowizja_proc:
        items.append(_item("prowizja", "Prowizja pośrednika z VAT", price * a.prowizja_proc / 100 * (1 + VAT),
                           "%g%% ceny + VAT" % a.prowizja_proc))
    if a.wykonczenie_m2 and area:
        items.append(_item("wykonczenie", "Wykończenie", a.wykonczenie_m2 * area, "%g zł/m²" % a.wykonczenie_m2))
    total = round(sum(i["kwota"] for i in items), 2)
    credit = None
    if loan > 0:
        payment = monthly_payment(loan, a.oprocentowanie, a.lata)
        credit = {"kwota": round(loan, 2), "rata": round(payment, 2), "lata": a.lata, "oprocentowanie": a.oprocentowanie,
                  "odsetki_razem": round(payment * a.lata * 12 - loan, 2)}
    fees = round((a.czynsz_m2 or 0) * (area or 0), 2)
    return {"cena": price, "rynek": "pierwotny" if primary else "wtorny", "jednorazowe": items,
            "razem_jednorazowe": total, "gotowka_na_start": round(price * a.wklad_proc / 100 + total, 2),
            "kredyt": credit,
            "miesiecznie": {"rata": credit["rata"] if credit else 0.0, "czynsz": fees,
                            "razem": round((credit["rata"] if credit else 0.0) + fees, 2)},
            "zalozenia": a.__dict__}
