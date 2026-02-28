"""
Built-in financial calculations for property development.
Called by Claude via tool use to ensure numerical precision.
"""
import numpy as np
from typing import List, Optional


def gross_yield(purchase_price: float, annual_rent: float) -> dict:
    if purchase_price <= 0:
        return {"error": "Purchase price must be positive"}
    yield_pct = (annual_rent / purchase_price) * 100
    return {
        "gross_yield_pct": round(yield_pct, 2),
        "annual_rent": annual_rent,
        "purchase_price": purchase_price,
        "weekly_rent": round(annual_rent / 52, 2),
    }


def net_yield(purchase_price: float, annual_rent: float, annual_costs: float) -> dict:
    if purchase_price <= 0:
        return {"error": "Purchase price must be positive"}
    net_income = annual_rent - annual_costs
    yield_pct = (net_income / purchase_price) * 100
    return {
        "net_yield_pct": round(yield_pct, 2),
        "net_annual_income": round(net_income, 2),
        "annual_costs": annual_costs,
    }


def development_margin(
    gross_realisation: float,
    total_development_cost: float,
) -> dict:
    if gross_realisation <= 0:
        return {"error": "Gross realisation must be positive"}
    margin = ((gross_realisation - total_development_cost) / gross_realisation) * 100
    profit = gross_realisation - total_development_cost
    return {
        "development_margin_pct": round(margin, 2),
        "profit": round(profit, 2),
        "gross_realisation": gross_realisation,
        "total_development_cost": total_development_cost,
        "return_on_cost_pct": round((profit / total_development_cost) * 100, 2) if total_development_cost > 0 else 0,
    }


def calculate_irr(cash_flows: List[float]) -> dict:
    """
    Calculate IRR from a list of cash flows.
    First element is typically negative (initial investment).
    """
    if len(cash_flows) < 2:
        return {"error": "Need at least 2 cash flows"}
    try:
        irr = np.irr(cash_flows) if hasattr(np, 'irr') else _numpy_irr(cash_flows)
        return {
            "irr_pct": round(irr * 100, 2),
            "cash_flows": cash_flows,
        }
    except Exception as e:
        return {"error": f"IRR calculation failed: {e}"}


def _numpy_irr(cash_flows: List[float], guess: float = 0.1) -> float:
    """Newton-Raphson IRR (numpy.irr was removed in numpy 1.24+)."""
    cf = np.array(cash_flows, dtype=float)
    rate = guess
    for _ in range(100):
        t = np.arange(len(cf))
        npv_val = np.sum(cf / (1 + rate) ** t)
        dnpv = np.sum(-t * cf / (1 + rate) ** (t + 1))
        if abs(dnpv) < 1e-12:
            break
        rate -= npv_val / dnpv
        if rate <= -1:
            rate = -0.999
    return rate


def calculate_npv(rate: float, cash_flows: List[float]) -> dict:
    """Calculate NPV given a discount rate and cash flows."""
    cf = np.array(cash_flows, dtype=float)
    t = np.arange(len(cf))
    npv_val = float(np.sum(cf / (1 + rate) ** t))
    return {
        "npv": round(npv_val, 2),
        "discount_rate_pct": round(rate * 100, 2),
    }


def loan_serviceability(
    loan_amount: float,
    annual_interest_rate: float,
    loan_term_years: int,
    annual_income: float,
) -> dict:
    """Calculate monthly repayment and serviceability metrics."""
    r = annual_interest_rate / 12
    n = loan_term_years * 12
    if r == 0:
        monthly_repayment = loan_amount / n
    else:
        monthly_repayment = loan_amount * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    annual_repayment = monthly_repayment * 12
    dscr = annual_income / annual_repayment if annual_repayment > 0 else 0
    lvr = (loan_amount / (loan_amount * 1.2)) * 100  # placeholder if no value given
    return {
        "monthly_repayment": round(monthly_repayment, 2),
        "annual_repayment": round(annual_repayment, 2),
        "dscr": round(dscr, 2),
        "loan_to_income_ratio": round(loan_amount / annual_income, 2) if annual_income > 0 else 0,
        "annual_interest_rate_pct": round(annual_interest_rate * 100, 2),
    }


def stamp_duty_estimate(purchase_price: float, state: str = "NSW") -> dict:
    """
    Rough stamp duty estimate for Australian states.
    Uses simplified progressive brackets. For indicative purposes only.
    """
    state = state.upper()
    # Simplified NSW brackets (2024)
    brackets = {
        "NSW": [
            (0, 17000, 0.014),
            (17000, 36000, 0.015),
            (36000, 97000, 0.0175),
            (97000, 360000, 0.035),
            (360000, 1084000, 0.045),
            (1084000, float("inf"), 0.055),
        ],
        "VIC": [
            (0, 25000, 0.014),
            (25000, 130000, 0.024),
            (130000, 960000, 0.06),
            (960000, float("inf"), 0.065),
        ],
        "QLD": [
            (0, 5000, 0),
            (5000, 75000, 0.015),
            (75000, 540000, 0.035),
            (540000, 1000000, 0.045),
            (1000000, float("inf"), 0.0575),
        ],
    }
    table = brackets.get(state, brackets["NSW"])
    duty = 0.0
    remaining = purchase_price
    for lo, hi, rate in table:
        if purchase_price <= lo:
            break
        taxable = min(purchase_price, hi) - lo
        duty += taxable * rate
    return {
        "stamp_duty_estimate": round(duty, 2),
        "purchase_price": purchase_price,
        "state": state,
        "note": "Indicative only. Consult a property lawyer for exact figures.",
    }
