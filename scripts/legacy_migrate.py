import os
import shutil
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy_root", default=r"d:\ALL_ABOUT_THE_JOB\MONEY\MONEY_LEGACY\NEW_TRADING_FULL\backend\app")
    ap.add_argument("--out_dir", default=r"d:\ALL_ABOUT_THE_JOB\MONEY\NAIRATRADING_HUB\legacy_reference")
    args = ap.parse_args()

    legacy = args.legacy_root
    out = args.out_dir
    targets = [
        os.path.join("data_fetchers", "ohlc_crypto_ccxt.py"),
        os.path.join("data_fetchers", "ohlc_mt5.py"),
        os.path.join("data_fetchers", "ohlc_csv.py"),
        os.path.join("services", "backtest_engine.py"),
        os.path.join("services", "signal_engine.py"),
    ]
    copied = []
    os.makedirs(out, exist_ok=True)
    for rel in targets:
        src = os.path.join(legacy, rel)
        if not os.path.exists(src):
            continue
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
    print({"legacy_root": legacy, "out_dir": out, "copied": copied})


if __name__ == "__main__":
    main()
