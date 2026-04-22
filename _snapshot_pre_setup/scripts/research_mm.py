import os
import sys
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine, NairaConfig

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT", help="Lista separada por comas")
    ap.add_argument("--provider", default="binance")
    ap.add_argument("--base_timeframe", default="1h")
    ap.add_argument("--timing_timeframe", default="15m")
    ap.add_argument("--max_bars", type=int, default=8000)
    ap.add_argument("--starting_cash", type=float, default=10000.0)
    ap.add_argument("--fee_bps", type=float, default=0.0)
    ap.add_argument("--include_fixed_qty", action="store_true")
    ap.add_argument("--bar_magnifier", action="store_true")
    ap.add_argument("--magnifier_timeframe", default="5m")
    args = ap.parse_args()

    symbols = [s.strip() for s in str(args.symbols).split(",") if s.strip()]
    provider = str(args.provider)
    tf = str(args.base_timeframe)
    timing_tf = str(args.timing_timeframe or "").strip()
    if timing_tf.lower() in ("off", "none", "0"):
        timing_tf = ""

    print("=" * 70)
    print(f" Portfolio Research - Multi Crypto ({provider}) TF={tf} cash={float(args.starting_cash):.2f} ")
    print("=" * 70)

    scenarios = []
    if bool(args.include_fixed_qty):
        scenarios.append({"name": "Lote Fijo (Qty=1.0)", "params": {"sizing_mode": "fixed_qty", "fixed_qty": 1.0}})
    scenarios.extend(
        [
            {"name": "Riesgo Fijo (1% por trade)", "params": {"sizing_mode": "fixed_risk", "risk_per_trade_pct": 1.0}},
            {
                "name": "Riesgo IA (0.25% - 1.5%)",
                "params": {"sizing_mode": "fixed_risk", "risk_per_trade_pct": 1.0, "ai_assisted_sizing": True, "ai_risk_min_pct": 0.25, "ai_risk_max_pct": 1.5},
            },
            {
                "name": "Martingala x2 (max 3, base 0.5%)",
                "params": {"sizing_mode": "martingale", "risk_per_trade_pct": 0.5, "martingale_mult": 2.0, "martingale_max_steps": 3},
            },
        ]
    )

    print(f"{'Symbol':<10} | {'Estrategia':<28} | {'Trades':>6} | {'WR':>7} | {'PF':>5} | {'MaxDD':>7} | {'CAGR':>7} | {'FinalEq':>10} | {'Signals':>7}")
    print("-" * 120)

    for symbol in symbols:
        cfg = NairaConfig(timing_timeframe=timing_tf, entry_mode="hybrid", use_structure_exits=False)
        engine = NairaEngine(data_dir=settings.DATA_DIR, config=cfg)
        model_path = os.path.join(settings.MODELS_DIR, f"naira_logreg_{symbol}_{provider}_{tf}.json")
        if os.path.exists(model_path):
            engine.load_model(model_path)

        for sc in scenarios:
            params = dict(sc["params"])
            params["collect_signal_stats"] = True
            params["bar_magnifier"] = bool(args.bar_magnifier)
            params["magnifier_timeframe"] = str(args.magnifier_timeframe)
            res = engine.backtest(
                symbol=symbol,
                provider=provider,
                base_timeframe=tf,
                starting_cash=float(args.starting_cash),
                fee_bps=float(args.fee_bps),
                max_bars=int(args.max_bars),
                feature_mode="fast",
                **params,
            )
            m = res.get("metrics", {}) or {}
            if "error" in m:
                print(f"{symbol:<10} | {sc['name']:<28} | ERROR: {m.get('error')}")
                continue
            sig = int(m.get("signals_entry_total") or 0)
            print(
                f"{symbol:<10} | {sc['name']:<28} | {int(m.get('trades', 0)):>6} | {float(m.get('win_rate_pct', 0.0)):>6.2f}%"
                f" | {float(m.get('profit_factor', 0.0)):>4.2f} | {float(m.get('max_drawdown_pct', 0.0)):>6.2f}%"
                f" | {float(m.get('CAGR_pct', 0.0)):>6.2f}% | ${float(m.get('equity_last', 0.0)):>9.2f} | {sig:>7}"
            )

        print("-" * 120)

if __name__ == "__main__":
    main()
