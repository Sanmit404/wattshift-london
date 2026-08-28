"""
Turns the 167 million row half hourly CSV into small panel files with DuckDB.

Everything downstream reads the parquet files written here, so this only has to
run once. On a laptop the first pass over the CSV takes a few minutes.

One thing worth knowing: the timestamps in the raw file mark the END of each half
hour, so the first reading of a day is stamped 00:30 and the last one is stamped
00:00 the next day. I shift every timestamp back 30 minutes so the date and time
of day refer to the start of the interval. Without that the last half hour of
every day gets counted on the wrong date.
"""

import os
import duckdb

RAW = "data/raw/CC_LCL-FullData.csv"
INTERIM = "data/interim"

# time of day blocks, by half hour index (0 = 00:00-00:30, 47 = 23:30-00:00)
# the peak block is the one the dToU tariff mostly targeted
BLOCKS = [
    ("night", 0, 13),      # 00:00 - 07:00
    ("morning", 14, 19),   # 07:00 - 10:00
    ("midday", 20, 31),    # 10:00 - 16:00
    ("peak", 32, 39),      # 16:00 - 20:00
    ("evening", 40, 47),   # 20:00 - 00:00
]


def block_case(col="hhod"):
    parts = []
    for name, lo, hi in BLOCKS:
        parts.append("WHEN %s BETWEEN %d AND %d THEN '%s'" % (col, lo, hi, name))
    return "CASE " + " ".join(parts) + " END"


def block_sizes():
    return {name: hi - lo + 1 for name, lo, hi in BLOCKS}


def main():
    os.makedirs(INTERIM, exist_ok=True)
    os.makedirs("data/tmp", exist_ok=True)

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='6GB'")
    con.execute("PRAGMA temp_directory='data/tmp'")

    readings = os.path.join(INTERIM, "readings.parquet")
    if not os.path.exists(readings):
        print("pass 1: csv -> readings.parquet")
        con.execute("""
            COPY (
                SELECT
                    hh,
                    grp,
                    CAST(ts AS DATE) AS d,
                    CAST(hour(ts) * 2 + minute(ts) / 30 AS TINYINT) AS hhod,
                    kwh
                FROM (
                    SELECT
                        LCLid AS hh,
                        stdorToU AS grp,
                        CAST(substr(DateTime, 1, 19) AS TIMESTAMP) - INTERVAL 30 MINUTE AS ts,
                        TRY_CAST(trim(kwh_raw) AS FLOAT) AS kwh
                    FROM read_csv(?,
                        header = true,
                        delim = ',',
                        columns = {
                            'LCLid': 'VARCHAR',
                            'stdorToU': 'VARCHAR',
                            'DateTime': 'VARCHAR',
                            'kwh_raw': 'VARCHAR'
                        })
                )
                WHERE kwh IS NOT NULL
            ) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)
        """ % readings, [RAW])

    con.execute("CREATE OR REPLACE VIEW r AS SELECT * FROM read_parquet('%s')" % readings)

    n_rows, n_hh = con.execute(
        "SELECT count(*), count(DISTINCT hh) FROM r").fetchone()
    print("readings kept:", n_rows, " households:", n_hh)

    print("pass 2: household day totals")
    con.execute("""
        CREATE OR REPLACE TABLE day AS
        SELECT hh, any_value(grp) AS grp, d,
               sum(kwh) AS kwh_day,
               count(*) AS n_read
        FROM r
        GROUP BY hh, d
    """)
    # a full day is 48 half hours. clock change days have 46 or 50 and the first
    # and last day a meter reports are usually partial, so drop anything else.
    con.execute("""
        COPY (SELECT hh, grp, d, kwh_day FROM day WHERE n_read = 48)
        TO '%s' (FORMAT PARQUET)
    """ % os.path.join(INTERIM, "hh_day.parquet"))

    print("pass 3: household month by time of day block")
    sizes = block_sizes()
    checks = " OR ".join(
        "(block = '%s' AND n_read = %d)" % (k, v) for k, v in sizes.items())
    con.execute("""
        CREATE OR REPLACE TABLE day_block AS
        SELECT hh, any_value(grp) AS grp, d, %s AS block,
               sum(kwh) AS kwh_day, count(*) AS n_read
        FROM r
        GROUP BY hh, d, block
    """ % block_case())
    con.execute("""
        COPY (
            SELECT hh, grp, date_trunc('month', d) AS m, block,
                   count(*) AS n_days, avg(kwh_day) AS kwh_day
            FROM day_block
            WHERE %s
            GROUP BY hh, grp, m, block
        ) TO '%s' (FORMAT PARQUET)
    """ % (checks, os.path.join(INTERIM, "hh_month_block.parquet")))

    print("pass 4: household month totals")
    con.execute("""
        COPY (
            SELECT hh, grp, date_trunc('month', d) AS m,
                   count(*) AS n_days, avg(kwh_day) AS kwh_day
            FROM day
            WHERE n_read = 48
            GROUP BY hh, grp, m
        ) TO '%s' (FORMAT PARQUET)
    """ % os.path.join(INTERIM, "hh_month.parquet"))

    print("pass 5: household coverage, for the attrition check")
    con.execute("""
        COPY (
            SELECT hh, any_value(grp) AS grp,
                   min(d) AS first_day, max(d) AS last_day,
                   count(*) AS n_days_any,
                   sum(CASE WHEN n_read = 48 THEN 1 ELSE 0 END) AS n_days_full
            FROM day
            GROUP BY hh
        ) TO '%s' (FORMAT PARQUET)
    """ % os.path.join(INTERIM, "households.parquet"))

    print("pass 6: group means per half hour of 2013, for the tariff signal check")
    con.execute("""
        COPY (
            SELECT d, hhod, grp,
                   avg(kwh) AS kwh,
                   count(*) AS n_hh
            FROM r
            WHERE d >= DATE '2013-01-01' AND d <= DATE '2013-12-31'
            GROUP BY d, hhod, grp
        ) TO '%s' (FORMAT PARQUET)
    """ % os.path.join(INTERIM, "group_halfhour_2013.parquet"))

    print("pass 7: average load shape by year and group, for the profile plot")
    con.execute("""
        COPY (
            SELECT year(d) AS yr, grp, hhod, avg(kwh) AS kwh, count(*) AS n
            FROM r
            WHERE year(d) IN (2012, 2013)
            GROUP BY yr, grp, hhod
        ) TO '%s' (FORMAT PARQUET)
    """ % os.path.join(INTERIM, "group_profile.parquet"))

    for f in sorted(os.listdir(INTERIM)):
        p = os.path.join(INTERIM, f)
        print("  %-30s %8.1f MB" % (f, os.path.getsize(p) / 1e6))


if __name__ == "__main__":
    main()
