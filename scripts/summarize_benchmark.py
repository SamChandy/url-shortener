"""Turn locust's CSV output into a small comparison table (also saved as summary.md)."""
import csv
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "benchmark_results"
SCENARIOS = [("with_redis", "With Redis cache"), ("without_redis", "Without cache (PostgreSQL only)")]


def aggregated_row(label: str) -> dict[str, str] | None:
    path = RESULTS / f"{label}_stats.csv"
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Name"] == "Aggregated":
                return row
    return None


def main() -> None:
    lines = [
        "| Scenario | Requests | Failures | Req/s | Median (ms) | p95 (ms) | p99 (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, title in SCENARIOS:
        row = aggregated_row(label)
        if row is None:
            lines.append(f"| {title} | not run | | | | | |")
            continue
        lines.append(
            f"| {title} | {row['Request Count']} | {row['Failure Count']} | "
            f"{float(row['Requests/s']):.1f} | {row['50%']} | {row['95%']} | {row['99%']} |"
        )
    table = "\n".join(lines)
    print("\n" + table + "\n")
    (RESULTS / "summary.md").write_text(table + "\n", encoding="utf-8")
    print(f"Saved to {RESULTS / 'summary.md'} - paste it into the README's benchmark section.")


if __name__ == "__main__":
    main()
