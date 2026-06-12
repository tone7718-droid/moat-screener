# -*- coding: utf-8 -*-
"""
update_data.py — GitHub Actions 자동 실행용 데이터 갱신 스크립트
top50_base.json(해자 상위 50) + moats_data.json(정성 분석)을 읽어
최신 가격·재무로 밸류에이션을 재계산하고 web_data.json을 갱신한다.
점수 기준은 valuation_top50.py와 동일:
  FCF수익률 40(8%↑만점) + EV/EBIT 30(10배↓만점) + PEG 30(1.0↓만점)
"""

import json
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

SLEEP_SEC = 1.0
BASE_JSON = "top50_base.json"
MOATS_JSON = "moats_data.json"
OUT_JSON = "web_data.json"

W_FCF, FCF_FULL = 40, 0.08
W_EVEBIT, EVEBIT_BEST, EVEBIT_WORST = 30, 10.0, 30.0
W_PEG, PEG_BEST, PEG_WORST = 30, 1.0, 3.0


def get_row(df, names):
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def latest(row):
    if row is None:
        return np.nan
    vals = row.dropna()
    if vals.empty:
        return np.nan
    return float(vals[sorted(vals.index)[-1]])


def fetch_valuation(ticker):
    import yfinance as yf
    t = yf.Ticker(ticker)

    price = np.nan
    try:
        price = float(t.fast_info["last_price"])
    except Exception:
        pass
    if np.isnan(price):
        try:
            price = float(t.history(period="5d")["Close"].iloc[-1])
        except Exception:
            pass

    info = {}
    try:
        info = t.info or {}
    except Exception:
        pass
    mcap = info.get("marketCap", np.nan)

    inc = t.income_stmt
    bal = t.balance_sheet
    cf = t.cashflow

    ebit = latest(get_row(inc, ["Operating Income", "EBIT"]))
    net_income_row = get_row(inc, ["Net Income"])
    ocf = latest(get_row(cf, ["Operating Cash Flow",
                              "Cash Flow From Continuing Operating Activities"]))
    capex = latest(get_row(cf, ["Capital Expenditure"]))
    debt = latest(get_row(bal, ["Total Debt"]))
    cash = latest(get_row(bal, ["Cash And Cash Equivalents",
                                "Cash Cash Equivalents And Short Term Investments"]))

    fcf = ocf + capex if (not np.isnan(ocf) and not np.isnan(capex)) else ocf

    ni_growth = np.nan
    ni_latest = np.nan
    if net_income_row is not None:
        ni = [float(net_income_row[c]) for c in sorted(net_income_row.index)
              if pd.notna(net_income_row[c])]
        if ni:
            ni_latest = ni[-1]
        if len(ni) >= 2 and ni[0] > 0 and ni[-1] > 0:
            ni_growth = (ni[-1] / ni[0]) ** (1 / (len(ni) - 1)) - 1

    fcf_yield = fcf / mcap if (not np.isnan(fcf) and mcap and mcap > 0) else np.nan
    ev = (mcap + (0 if np.isnan(debt) else debt) - (0 if np.isnan(cash) else cash)) \
        if (mcap and mcap > 0) else np.nan
    ev_ebit = ev / ebit if (not np.isnan(ev) and not np.isnan(ebit) and ebit > 0) else np.nan
    per = mcap / ni_latest if (mcap and not np.isnan(ni_latest) and ni_latest > 0) else np.nan
    peg = per / (ni_growth * 100) if (not np.isnan(per) and not np.isnan(ni_growth)
                                      and ni_growth > 0) else np.nan

    return {"price": None if np.isnan(price) else round(price, 2),
            "fcf_yield": None if np.isnan(fcf_yield) else round(fcf_yield, 4),
            "ev_ebit": None if np.isnan(ev_ebit) else round(ev_ebit, 1),
            "per": None if np.isnan(per) else round(per, 1),
            "ni_growth": None if np.isnan(ni_growth) else round(ni_growth, 4),
            "peg": None if np.isnan(peg) else round(peg, 2)}


def valuation_score(v):
    s = 0.0
    parts = []
    if v["fcf_yield"] is not None:
        pts = W_FCF * float(np.clip(v["fcf_yield"] / FCF_FULL, 0, 1))
        s += pts
        parts.append(f"FCF수익률 {v['fcf_yield']*100:.1f}% → {pts:.0f}/{W_FCF}점")
    else:
        parts.append(f"FCF수익률 계산불가 → 0/{W_FCF}점")
    if v["ev_ebit"] is not None:
        pts = W_EVEBIT * float(np.clip(
            (EVEBIT_WORST - v["ev_ebit"]) / (EVEBIT_WORST - EVEBIT_BEST), 0, 1))
        s += pts
        parts.append(f"EV/EBIT {v['ev_ebit']:.1f}배 → {pts:.0f}/{W_EVEBIT}점")
    else:
        parts.append(f"EV/EBIT 계산불가 → 0/{W_EVEBIT}점")
    if v["peg"] is not None:
        pts = W_PEG * float(np.clip(
            (PEG_WORST - v["peg"]) / (PEG_WORST - PEG_BEST), 0, 1))
        s += pts
        g = f"{v['ni_growth']*100:.0f}%" if v["ni_growth"] is not None else "?"
        parts.append(f"PEG {v['peg']:.2f}(PER {v['per']}, 성장 {g}) → {pts:.0f}/{W_PEG}점")
    elif v["ni_growth"] is not None and v["ni_growth"] <= 0:
        parts.append(f"이익 역성장 → PEG 0/{W_PEG}점")
    else:
        parts.append(f"PEG 계산불가 → 0/{W_PEG}점")

    score = round(s, 1)
    if score >= 70:
        grade = "저평가 가능성(추정)"
    elif score >= 40:
        grade = "적정 범위(추정)"
    else:
        grade = "고평가 가능성(추정)"
    return score, grade, " / ".join(parts)


def main():
    with open(BASE_JSON, encoding="utf-8") as f:
        base = json.load(f)
    with open(MOATS_JSON, encoding="utf-8") as f:
        moats = json.load(f)

    rows = []
    fail = 0
    for i, b in enumerate(base, 1):
        ticker = b["ticker"]
        try:
            v = fetch_valuation(ticker)
            score, grade, rationale = valuation_score(v)
            if v["price"] is None:
                fail += 1
        except Exception as e:
            v = {"price": None, "fcf_yield": None, "ev_ebit": None,
                 "per": None, "ni_growth": None, "peg": None}
            score, grade, rationale = None, "조회실패", f"{type(e).__name__}"
            fail += 1
        m = moats.get(ticker, {})
        rows.append({
            "ticker": ticker, "name": b["name"], "sector": b["sector"],
            "moat_score": b["moat_score"],
            "val_score": score, "val_grade": grade, "rationale": rationale,
            **v,
            "biz": m.get("biz", ""), "moat": m.get("moat", ""),
            "moat_type": m.get("moat_type", ""), "risk": m.get("risk", ""),
        })
        print(f"[{i}/{len(base)}] {ticker}: {grade}", flush=True)
        time.sleep(SLEEP_SEC)

    # 절반 이상 실패하면 기존 데이터를 덮어쓰지 않고 중단 (데이터 보호)
    if fail > len(base) / 2:
        print(f"[중단] {fail}/{len(base)} 조회 실패 — 기존 web_data.json 유지")
        sys.exit(1)

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "method": {
            "moat": "해자점수(0~100): ROIC 수준·지속성 50 + 매출총이익률 수준·안정성 30 + FCF/희석/성장 20",
            "valuation": "밸류점수(0~100): FCF수익률 40(8%↑만점) + EV/EBIT 30(10배↓만점) + PEG 30(1.0↓만점)",
            "disclaimer": "투자 권유 아님. 데이터: Yahoo Finance(무료, 최대 4개년). 최종 판단과 책임은 사용자에게 있음.",
        },
        "companies": rows,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"갱신 완료: {OUT_JSON} (실패 {fail}건)")


if __name__ == "__main__":
    main()
