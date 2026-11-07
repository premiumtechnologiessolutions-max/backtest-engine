# Historical XAUUSD input — local only

Place the original annual JSON ZIP here on your own trusted machine if needed. Do **not** commit raw historical data, credentials, or generated multi-gigabyte Parquet files to GitHub.

Use the CLI import command and inspect manifest.json. ZIP format expected:
- 2010 (1).json, 2011.json, ..., 2026.json
- each file contains a JSON array
- each candle has ts (UNIX UTC seconds), o/h/l/c (BID), ao/ah/al/ac (ASK) and optional v.

The importer never alters or interpolates the raw archive. It rejects anomalous year partitions for manual review.
