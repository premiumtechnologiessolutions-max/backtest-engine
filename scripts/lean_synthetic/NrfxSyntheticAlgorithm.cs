using System;
using System.Globalization;
using QuantConnect;
using QuantConnect.Algorithm;
using QuantConnect.Data;

namespace Nrfx.LeanSynthetic
{
    public sealed class NrfxSyntheticAlgorithm : QCAlgorithm
    {
        private Symbol _symbol;
        private int _expectedBars;
        private int _seen;

        public override void Initialize()
        {
            SetTimeZone("Etc/UTC");
            SetStartDate(2020, 1, 5);
            SetEndDate(2020, 1, 8);
            SetCash(100000);
            SetBenchmark(_ => 1m);
            _expectedBars = int.Parse(GetParameter("bars"), CultureInfo.InvariantCulture);
            _symbol = AddForex("EURUSD", Resolution.Minute, Market.Oanda, fillForward: false).Symbol;
        }

        public override void OnData(Slice slice)
        {
            if (!slice.QuoteBars.TryGetValue(_symbol, out var quote) || quote.IsFillForward)
            {
                return;
            }

            _seen++;
            if (_seen % 20 == 2 && _seen + 10 <= _expectedBars)
            {
                MarketOrder(_symbol, 1000, tag: "nrfx-synthetic-enter");
            }
            else if (_seen % 20 == 12 && Portfolio[_symbol].Quantity == 1000)
            {
                MarketOrder(_symbol, -1000, tag: "nrfx-synthetic-exit");
            }
        }

        public override void OnEndOfAlgorithm()
        {
            if (_seen != _expectedBars || Portfolio[_symbol].Quantity != 0)
            {
                throw new InvalidOperationException("Synthetic quote count or final position mismatch.");
            }
            SetRuntimeStatistic("NRFX Synthetic Bars", _seen.ToString(CultureInfo.InvariantCulture));
        }
    }
}
