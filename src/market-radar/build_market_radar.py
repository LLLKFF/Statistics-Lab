#!/usr/bin/env python3
"""Build a dated, auditable Market Radar from the agreed 98-symbol registry.

Requires: pip install 'yfinance>=0.2.65' pandas numpy
Run: python build_market_radar.py --output snapshots
No cached data are ever promoted to a successful snapshot.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
RATE_TICKERS = {"^FVX", "^TNX", "^TYX", "^IRX"}
PRICE_FIELDS = ["Open", "High", "Low", "Close", "Volume"]
METRICS = [
    "return_1d_pct", "return_5d_pct", "return_20d_pct", "return_63d_pct",
    "ema20", "ema100", "ema200", "distance_ema20_pct", "distance_ema100_pct",
    "distance_ema200_pct", "vol_20d_annualized_pct", "atr_14",
    "distance_20d_high_pct", "distance_252d_high_pct", "volume_zscore_20d",
    "relative_strength_20d_pp", "trend_score", "momentum_score", "yield_change_1d_bp",
    "ema20_slope_5d_pct", "ema100_slope_20d_pct", "ema200_slope_20d_pct",
    "ema_alignment", "ema_structure_score", "volume_ratio_20d",
    "price_volume_turnover_proxy", "reported_turnover_usd", "volume_price_action", "cmf20", "obv_delta_20d_normalized",
]


def clean(x):
    if isinstance(x, (np.integer, int)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return round(float(x), 5) if math.isfinite(float(x)) else None
    if pd.isna(x):
        return None
    return x


def pct(a, b):
    return clean((a / b - 1) * 100) if b is not None and b != 0 else None


def value_at(s, lag):
    return float(s.iloc[-lag - 1]) if len(s) > lag else None


def ema_slope(ema, lag):
    """Percent change in an EMA versus `lag` bars earlier."""
    if len(ema) <= lag or pd.isna(ema.iloc[-1]) or pd.isna(ema.iloc[-lag - 1]):
        return None
    current = float(ema.iloc[-1])
    previous = float(ema.iloc[-lag - 1])
    return clean((current / previous - 1) * 100) if previous else None


def downloaded_frame(block, ticker):
    if block.empty:
        return pd.DataFrame()
    if isinstance(block.columns, pd.MultiIndex):
        if ticker in block.columns.get_level_values(0):
            frame = block[ticker].copy()
        elif ticker in block.columns.get_level_values(1):
            frame = block.xs(ticker, axis=1, level=1).copy()
        else:
            return pd.DataFrame()
    else:
        frame = block.copy()
    frame = frame.loc[:, [c for c in PRICE_FIELDS if c in frame.columns]]
    if "Close" not in frame.columns:
        return pd.DataFrame()
    return frame.dropna(subset=["Close"]).sort_index()


def make_metrics(frame, benchmark, volume_is_usd_turnover=False):
    c = frame["Close"].astype(float).dropna()
    out = dict.fromkeys(METRICS)
    for days in (1, 5, 20, 63):
        out[f"return_{days}d_pct"] = pct(float(c.iloc[-1]), value_at(c, days))
    emas = {}
    for window in (20, 100, 200):
        ema = c.ewm(span=window, adjust=False, min_periods=window).mean()
        emas[window] = ema
        if pd.notna(ema.iloc[-1]):
            value = float(ema.iloc[-1])
            out[f"ema{window}"] = clean(value)
            out[f"distance_ema{window}_pct"] = pct(float(c.iloc[-1]), value)
    out["ema20_slope_5d_pct"] = ema_slope(emas[20], 5)
    out["ema100_slope_20d_pct"] = ema_slope(emas[100], 20)
    out["ema200_slope_20d_pct"] = ema_slope(emas[200], 20)
    if all(out.get(f"ema{x}") is not None for x in (20, 100, 200)):
        ema20, ema100, ema200 = (out[f"ema{x}"] for x in (20, 100, 200))
        out["ema_alignment"] = (
            "bullish_stack" if ema20 > ema100 > ema200 else
            "bearish_stack" if ema20 < ema100 < ema200 else "mixed"
        )
        gates = [out[f"distance_ema{x}_pct"] > 0 for x in (20, 100, 200)]
        gates.append(out["ema100_slope_20d_pct"] is not None and out["ema100_slope_20d_pct"] > 0)
        gates.append(ema100 > ema200)
        out["ema_structure_score"] = sum(gates)
    if len(c) >= 21:
        out["vol_20d_annualized_pct"] = clean(c.pct_change().tail(20).std(ddof=1) * np.sqrt(252) * 100)
    if {"High", "Low"}.issubset(frame.columns):
        high, low, prev = frame["High"].astype(float), frame["Low"].astype(float), c.shift(1)
        tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
        if tr.dropna().shape[0] >= 14:
            out["atr_14"] = clean(tr.tail(14).mean())
        for window in (20, 252):
            h = high.tail(window).max() if len(high.dropna()) >= window else None
            out[f"distance_{window}d_high_pct"] = pct(float(c.iloc[-1]), float(h)) if h else None
    if "Volume" in frame.columns:
        volume = pd.to_numeric(frame["Volume"], errors="coerce").dropna()
        if len(volume) >= 21:
            baseline = volume.iloc[-21:-1]
            latest_volume = float(volume.iloc[-1])
            if latest_volume > 0 and baseline.mean() > 0:
                out["volume_ratio_20d"] = clean(latest_volume / float(baseline.mean()))
            if len(baseline) == 20 and baseline.std(ddof=1) > 0:
                out["volume_zscore_20d"] = clean((latest_volume - baseline.mean()) / baseline.std(ddof=1))
            if "Close" in frame.columns and latest_volume >= 0:
                close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
                # Keep provider units explicit: this is price x volume, not net flow.
                if latest_volume > 0 and len(close) and close.index[-1] == volume.index[-1]:
                    if volume_is_usd_turnover:
                        out["reported_turnover_usd"] = clean(latest_volume)
                    else:
                        out["price_volume_turnover_proxy"] = clean(float(close.iloc[-1]) * latest_volume)
                    if out["return_1d_pct"] is not None:
                        ratio = out["volume_ratio_20d"]
                        activity = "high" if ratio is not None and ratio >= 1.5 else "low" if ratio is not None and ratio < 0.8 else "normal"
                        direction = "up" if out["return_1d_pct"] > 0 else "down" if out["return_1d_pct"] < 0 else "flat"
                        out["volume_price_action"] = f"{direction}_{activity}_volume"
        # CMF and normalized OBV are volume-derived pressure proxies, not observed net fund flows.
        if {"High", "Low", "Close"}.issubset(frame.columns) and len(frame) >= 20:
            block = frame[["High", "Low", "Close", "Volume"]].apply(pd.to_numeric, errors="coerce").tail(20).dropna()
            if len(block) == 20 and block["Volume"].sum() > 0:
                spread = (block["High"] - block["Low"]).replace(0, np.nan)
                clv = ((2 * block["Close"] - block["High"] - block["Low"]) / spread).fillna(0)
                out["cmf20"] = clean(float((clv * block["Volume"]).sum() / block["Volume"].sum()))
        if "Close" in frame.columns and len(volume) >= 21:
            close = pd.to_numeric(frame["Close"], errors="coerce")
            aligned = pd.concat([close.rename("close"), pd.to_numeric(frame["Volume"], errors="coerce").rename("volume")], axis=1).dropna().tail(21)
            if len(aligned) == 21 and aligned["volume"].iloc[:-1].sum() > 0:
                signs = np.sign(aligned["close"].diff().fillna(0))
                obv = (signs * aligned["volume"]).cumsum()
                out["obv_delta_20d_normalized"] = clean(
                    (float(obv.iloc[-1]) - float(obv.iloc[0])) / float(aligned["volume"].iloc[:-1].sum())
                )
    if benchmark is not None and out["return_20d_pct"] is not None:
        # Align by daily observation date; do not compare different calendar endpoints.
        left = c.copy()
        right = benchmark["Close"].dropna().astype(float).copy()
        left.index, right.index = left.index.date, right.index.date
        overlap = pd.concat([left.rename("asset"), right.rename("benchmark")], axis=1, join="inner").dropna()
        if len(overlap) >= 21 and overlap.index[-1] == c.index[-1].date():
            out["relative_strength_20d_pp"] = clean(
                (overlap.asset.iloc[-1] / overlap.asset.iloc[-21]
                 - overlap.benchmark.iloc[-1] / overlap.benchmark.iloc[-21]) * 100
            )
    checks = [out["distance_ema20_pct"], out["distance_ema100_pct"], out["distance_ema200_pct"], out["return_20d_pct"]]
    out["trend_score"] = sum(v > 0 for v in checks) if all(v is not None for v in checks) else None
    mom = [out["return_5d_pct"], out["return_20d_pct"], out["return_63d_pct"]]
    out["momentum_score"] = sum(v > 0 for v in mom) if all(v is not None for v in mom) else None
    return out


def summarize_market_breadth(rows):
    """Cross-sectional EMA breadth for common-date US equities, grouped by sector."""
    universe = [r for r in rows if r.get("asset_class") == "equity" and r.get("active", "true").lower() == "true"]
    dates = [r.get("bar_date") for r in universe if r.get("status") == "ok" and r.get("bar_date")]
    cutoff = max(dates) if dates else None
    matched = [r for r in universe if r.get("status") == "ok" and r.get("bar_date") == cutoff]

    def group_summary(group, requested=None):
        requested = len(group) if requested is None else requested
        out = {"requested": requested, "matched_cutoff": len(group),
               "excluded_or_missing_at_cutoff": requested - len(group)}
        for window in (20, 100, 200):
            field = f"distance_ema{window}_pct"
            valid = [r for r in group if r.get(field) is not None]
            above = sum(float(r[field]) > 0 for r in valid)
            out[f"above_ema{window}"] = {
                "valid": len(valid), "above": above,
                "pct_above": clean(above / len(valid) * 100) if valid else None,
            }
        return out

    sectors = {}
    for sector in sorted({r.get("sector") or "Unclassified" for r in universe}):
        sector_matched = [r for r in matched if (r.get("sector") or "Unclassified") == sector]
        sector_requested = sum((r.get("sector") or "Unclassified") == sector for r in universe)
        sectors[sector] = group_summary(sector_matched, sector_requested)
    return {
        "bar_date": cutoff,
        "universe": "active US equities only; ETFs, leveraged ETFs, crypto, rates and futures excluded",
        "requested_equities": len(universe), "matched_cutoff": len(matched),
        "excluded_or_missing_at_cutoff": len(universe) - len(matched),
        "overall": group_summary(matched), "by_sector": sectors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "snapshots"))
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--period", default="18mo", help="Enough daily bars for 200/252-day indicators")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 20:
        parser.error("--batch-size must be 1..20")
    start = datetime.now(timezone.utc)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    registry = list(csv.DictReader((ROOT / "asset_pool.csv").open(encoding="utf-8-sig", newline="")))
    active = [r for r in registry if r["active"].lower() == "true"]
    tickers = [r["ticker"] for r in active]
    if len(tickers) != 98 or len(set(tickers)) != len(tickers):
        raise ValueError("Expected 98 unique active tickers; check the registry")
    frames, errors = {}, {}
    source_messages = []

    class Capture(logging.Handler):
        def emit(self, record):
            source_messages.append(record.getMessage())

    capture = Capture(level=logging.WARNING)
    logging.getLogger("yfinance").addHandler(capture)
    for offset in range(0, len(tickers), args.batch_size):
        group = tickers[offset:offset + args.batch_size]
        try:
            block = yf.download(group, period=args.period, interval="1d", auto_adjust=True,
                                group_by="ticker", threads=False, progress=False, timeout=12)
            for t in group:
                f = downloaded_frame(block, t)
                if f.empty:
                    errors[t] = "No daily bars returned by yfinance (check HTTP 429 / ticker availability)"
                else:
                    frames[t] = f
        except Exception as exc:
            for t in group:
                errors[t] = f"{type(exc).__name__}: {str(exc)[:180]}"
        print(f"batch {offset // args.batch_size + 1}: {len(frames)}/{len(tickers)} fetched", file=sys.stderr, flush=True)
        # A fully empty first batch indicates source-wide failure. Stop promptly.
        if offset == 0 and not frames:
            for t in tickers[len(group):]:
                errors[t] = "Skipped after first batch returned no data; source unavailable"
            break
    now = datetime.now(timezone.utc)
    rows = []
    for r in active:
        t = r["ticker"]
        f = frames.get(t)
        row = dict(r)
        row.update({"status": "unavailable", "bar_date": None, "last_close": None,
                    "quote_unit": "percent yield" if t in RATE_TICKERS else "quote currency / index points",
                    "volume_unit": ("shares" if r["asset_class"] in {"equity", "etf", "leveraged_etf"}
                                    else "contracts" if r["asset_class"] == "future"
                                    else "coin units" if r["asset_class"] == "crypto" else None),
                    "error": errors.get(t), **dict.fromkeys(METRICS)})
        if f is not None and not f.empty:
            c = f["Close"].astype(float).dropna()
            row["status"] = "ok" if (now.date() - c.index[-1].date()).days <= (2 if r["asset_class"] == "crypto" else 5) else "stale"
            row["bar_date"] = str(c.index[-1].date())
            row["last_close"] = clean(c.iloc[-1])
            row["error"] = None
            if t in RATE_TICKERS:
                row["yield_change_1d_bp"] = clean((c.iloc[-1] - c.iloc[-2]) * 100) if len(c) >= 2 else None
            else:
                b = frames.get(r["benchmark"]) if r["benchmark"] != t else None
                row.update(make_metrics(f, b))
        rows.append(row)
    ok = sum(r["status"] == "ok" for r in rows)
    stale = sum(r["status"] == "stale" for r in rows)
    status = "complete" if ok == len(rows) else ("partial" if ok else "unavailable")
    snapshot = {
        "schema_version": "market-radar/1.0", "generated_at_utc": now.isoformat(),
        "feature_schema_version": "market-features/1.2",
        "source": f"yfinance {yf.__version__} / Yahoo Finance daily bars (auto_adjust=True)",
        "status": status,
        "source_error": "Yahoo Finance rate limited this run (HTTP 429)" if any("429" in m or "RateLimit" in m for m in source_messages) else ("No bars returned by yfinance" if not frames else None),
        "coverage": {"requested": len(rows), "fresh": ok, "stale": stale, "unavailable": len(rows)-ok-stale},
        "market_regime": None, "market_regime_reason": "Insufficient verified data" if status != "complete" else "Regime classification is not yet defined",
        "notes": ["Trading-day returns use N preceding bars; crypto daily bars may have a different cutoff.",
                  "Rates ^FVX/^TNX/^TYX/^IRX are yield quotes in percentage points; changes are basis points, and price return fields are null.",
                  "^FVX is 5-year and ^IRX is 13-week, neither is a 2-year yield. 2-year yield is excluded until a reliable source is added.",
                  "GC=F and CL=F are rolling futures proxies, not spot; SOXL is a daily 3x leveraged ETF.",
                  "EMA convention: span=20/100/200, adjust=False, min_periods=span. EMA20 slope compares 5 bars earlier; EMA100/200 slopes compare 20 bars earlier.",
                  "Trend score = count of above EMA20/100/200 and positive 20-bar return (0..4); momentum score = positive 5/20/63-bar returns (0..3).",
                  "Feature v1.2 uses EMA20/100/200 for trend alignment, slopes, structure score, and common-date equity breadth; volume and pressure proxy fields are unchanged.",
                  "CMF20 and normalized OBV are price-volume pressure proxies, not measured net fund flows. Price x volume is a turnover proxy; provider units vary by asset type.",
                  "No market calls or published performance metrics are generated on missing data."],
        "assets": rows,
        "market_participation": summarize_market_breadth(rows),
    }
    stem = f"market_radar_{start:%Y-%m-%d_%H%M%S}Z"
    json_path = output / f"{stem}.json"
    csv_path = output / f"{stem}.csv"
    md_path = output / f"{stem}.md"
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    key = ["SPY", "QQQ", "IWM", "^VIX", "^TNX", "DX-Y.NYB", "GC=F", "CL=F", "NVDA", "MU", "SNDK", "SOXL", "BTC-USD", "ETH-USD", "MSTR", "CRCL"]
    by_ticker = {r["ticker"]: r for r in rows}
    fmt = lambda v, suffix="": "—" if v is None else f"{v:+.2f}{suffix}" if isinstance(v, (float, int)) and suffix else f"{v:.2f}" if isinstance(v, (float, int)) else str(v)
    lines = ["# Statistics Lab · Market Radar v1.0", "", f"生成时间（UTC）：{now:%Y-%m-%d %H:%M:%S}",
             f"数据源：yfinance {yf.__version__}，Yahoo Finance 日线", f"状态：**{status}**；有效 {ok}/{len(rows)}，过期 {stale}，缺失 {len(rows)-ok-stale}。", ""]
    if not ok:
        lines += ["**本次未取得行情，以下仅为资产覆盖清单，不构成最新市场判断。**", f"抓取诊断：{snapshot['source_error']}。CSV/JSON 的错误字段记录逐个资产的状态。", ""]
    lines += ["| 标的 | 最新日线日期 | 收盘值 | 1D | 5D | 20D | 距 EMA100 | 20D 相对强度 | 状态 |", "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for t in key:
        r = by_ticker[t]
        lines.append(f"| {t} | {r['bar_date'] or '—'} | {fmt(r['last_close'])} | {fmt(r['return_1d_pct'], '%')} | {fmt(r['return_5d_pct'], '%')} | {fmt(r['return_20d_pct'], '%')} | {fmt(r['distance_ema100_pct'], '%')} | {fmt(r['relative_strength_20d_pp'], 'pp')} | {r['status']} |")
    lines += ["", "## 指标口径与使用边界", "", *[f"- {n}" for n in snapshot["notes"]], "", "完整的 98 标的逐项数据、缺失状态和指标见同时间戳 CSV/JSON；后续任务应读取 JSON 的 `status` 和 `coverage`，仅使用 `status=ok` 的行。", ""]
    breadth = snapshot["market_participation"]
    lines += ["", "## 市场广度（普通美股，按共同交易日）", "", f"统计日：{breadth['bar_date'] or '—'}；共同日期覆盖 {breadth['matched_cutoff']}/{breadth['requested_equities']} 只。", "", "| 分组 | EMA20上方 | EMA100上方 | EMA200上方 |", "|---|---:|---:|---:|"]
    def breadth_pct(obj, key):
        val = obj[key]["pct_above"]
        return "—" if val is None else f"{val:.1f}% ({obj[key]['above']}/{obj[key]['valid']})"
    lines.append("| 全部普通美股 | " + " | ".join(breadth_pct(breadth["overall"], f"above_ema{x}") for x in (20, 100, 200)) + " |")
    for sector, values in breadth["by_sector"].items():
        lines.append(f"| {sector} | " + " | ".join(breadth_pct(values, f"above_ema{x}") for x in (20, 100, 200)) + " |")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": status, "coverage": snapshot["coverage"], "files": [str(json_path), str(csv_path), str(md_path)]}, ensure_ascii=False))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
