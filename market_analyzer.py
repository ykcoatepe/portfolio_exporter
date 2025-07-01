
"""
market_analyzer.py - Your new, unified market analysis tool.

Usage:
  python market_analyzer.py --mode pre-market  # For daily pre-market report
  python market_analyzer.py --mode live        # For a real-time data feed
  python market_analyzer.py --greeks           # To include portfolio greeks
  python market_analyzer.py --option-chain SPY # To fetch option chain for a symbol
"""
import argparse
import pandas as pd
from datetime import datetime, timedelta
from utils.ib import IBManager, load_ib_positions_ib, get_option_positions, load_tickers, fetch_ib_quotes, fetch_yf_quotes, fetch_fred_yields, fetch_live_positions
from utils.technicals import calculate_indicators
from utils.analysis import get_greeks, get_option_chain, get_technical_signals, get_historical_prices




def pre_market_analysis(ib_manager):
    """Generates the pre-market analysis report."""
    with ib_manager as ib:
        positions = load_ib_positions_ib(ib)
        tickers = positions['symbol'].unique().tolist() if not positions.empty else []
        
        if not tickers:
            print("No positions found. Using default tickers.")
            tickers = ['SPY', 'QQQ', 'IWM']

        hist_data = get_historical_prices(tickers)
        tech_data = calculate_indicators(hist_data)

        print("--- Pre-Market Analysis ---")
        print("\n--- Positions ---")
        print(positions)
        print("\n--- Technicals (Last Day) ---")
        print(tech_data.groupby('ticker').last())

        # Macro overview (price & % chg vs yesterday close)
        MARKET_OVERVIEW = {
            "SPY": "S&P 500", "QQQ": "Nasdaq 100", "IWM": "Russell 2000",
            "VIX": "VIX Index", "DXY": "US Dollar", "TLT": "US 20Y Bond",
            "IEF": "US 7-10Y Bond", "GC=F": "Gold Futures", "CL=F": "WTI Oil",
            "BTC-USD": "Bitcoin",
        }
        
        INDICATORS = [
            "pct_change", "sma20", "ema20", "rsi14", "macd", "macd_signal",
            "atr14", "bb_upper", "bb_lower", "real_vol_30", "adx14"
        ]

        tech_last = tech_data.groupby('ticker').last()[INDICATORS].round(3)
        macro_px = tech_last[['pct_change']].copy()
        macro_px.columns = ['pct_change']
        macro_px.insert(0, 'close', tech_data.groupby('ticker').last()['close'].round(3))
        macro_px.insert(0, 'name', [MARKET_OVERVIEW.get(t, t) for t in tech_last.index])
        macro_px.index.name = 'ticker'
        macro_px['close'] = macro_px['close'].round(3)
        macro_px['pct_change'] = (macro_px['pct_change'] * 100).round(3)

        print("\n--- Macro Overview ---")
        print(macro_px)

def live_analysis(ib_manager):
    """Provides a live feed of market data."""
    with ib_manager as ib:
        tickers = load_tickers(ib)
        opt_list, opt_under = get_option_positions(ib)
        tickers = sorted(set(tickers + list(opt_under)))

        if not tickers:
            print("No tickers found for live analysis.")
            return

        df_ib = fetch_ib_quotes(ib, tickers, opt_list)
        served = set(df_ib['ticker']) if not df_ib.empty else set()
        remaining = [t for t in tickers if t not in served]

        df_yf = fetch_yf_quotes(remaining) if remaining else pd.DataFrame()
        df_fred = fetch_fred_yields([t for t in remaining if t.startswith("US")]) if remaining else pd.DataFrame()

        df = pd.concat([df_ib, df_yf, df_fred], ignore_index=True)
        
        # Live positions snapshot and unrealized PnL merge
        pnl_map = {}
        pct_map = {}
        df_pos = fetch_live_positions(ib)
        if not df_pos.empty:
            pnl_map = df_pos.groupby("ticker")["unrealized_pnl"].sum().to_dict()
            cost_map = df_pos.groupby("ticker")["cost_basis"].sum().to_dict()
            pct_map = {s: (100 * pnl_map[s] / cost_map[s]) if cost_map[s] else np.nan for s in pnl_map}

        df["unrealized_pnl"] = df["ticker"].map(pnl_map)
        df["unrealized_pnl_pct"] = df["ticker"].map(pct_map)

        print("--- Live Market Data ---")
        print(df)

def technical_signals_analysis(ib_manager):
    """Performs technical signals analysis."""
    with ib_manager as ib:
        positions = load_ib_positions_ib(ib)
        tickers = positions['symbol'].unique().tolist() if not positions.empty else []
        if not tickers:
            print("No positions found. Using default tickers.")
            tickers = ['SPY', 'QQQ', 'IWM']
        
        tech_signals_df = get_technical_signals(ib, tickers)
        print("--- Technical Signals ---")
        print(tech_signals_df)

def greeks_analysis(ib_manager):
    """Performs portfolio greeks analysis."""
    with ib_manager as ib:
        greeks_df = get_greeks(ib)
        print("--- Portfolio Greeks ---")
        print(greeks_df)

def option_chain_analysis(ib_manager, symbol):
    """Fetches and displays the option chain for a given symbol."""
    with ib_manager as ib:
        option_chain_df = get_option_chain(ib, symbol)
        print(f"--- Option Chain for {symbol} ---")
        print(option_chain_df)


def main():
    parser = argparse.ArgumentParser(description="Unified market analysis tool.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--mode", choices=["pre-market", "live", "tech-signals"], help="Analysis mode.")
    group.add_argument("--greeks", action="store_true", help="Portfolio greeks analysis.")
    group.add_argument("--option-chain", type=str, metavar="SYMBOL", help="Fetch option chain for a symbol.")

    args = parser.parse_args()

    ib_manager = IBManager()

    if args.mode == "pre-market":
        pre_market_analysis(ib_manager)
    elif args.mode == "live":
        live_analysis(ib_manager)
    elif args.mode == "tech-signals":
        technical_signals_analysis(ib_manager)
    elif args.greeks:
        greeks_analysis(ib_manager)
    elif args.option_chain:
        option_chain_analysis(ib_manager, args.option_chain)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
