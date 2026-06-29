#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
from pathlib import Path

ACTIVE_STATUSES = {"upcoming", "active", "breaking", "active market reaction", "released"}


def main():
    p = argparse.ArgumentParser(description="Append an event entry to event-pool.md.")
    p.add_argument("--file", default=str(Path(__file__).resolve().parents[1] / "references" / "event-pool.md"))
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--status", choices=["upcoming", "active", "breaking", "released", "active market reaction", "resolved", "archived", "past"], required=True)
    p.add_argument("--expires-at", help="Required for active/upcoming/breaking/released/active market reaction events unless --next-recheck is set.")
    p.add_argument("--next-recheck", help="Required for active/upcoming/breaking/released/active market reaction events unless --expires-at is set.")
    p.add_argument("--time", default=datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z"))
    args = p.parse_args()

    if args.status in ACTIVE_STATUSES and not (args.expires_at or args.next_recheck):
        raise SystemExit("Active events require --expires-at or --next-recheck.")

    path = Path(args.file)
    metadata = [f"- Status: {args.status}"]
    if args.expires_at:
        metadata.append(f"- Expires at: {args.expires_at}")
    if args.next_recheck:
        metadata.append(f"- Next recheck: {args.next_recheck}")
    entry = f"\n\n### {args.time} - {args.title}\n\n" + "\n".join(metadata) + f"\n\n{args.body.strip()}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(entry)
    print(path)


if __name__ == "__main__":
    main()
