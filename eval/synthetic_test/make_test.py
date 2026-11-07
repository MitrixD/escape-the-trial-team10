"""Build a synthetic A/B test inside a copy of the offline Lumen dataset.

Test: "AI limit: annual upfront vs weekly trial" on placement ai_limit_reached.
  arm annual_upfront : P_A of users buy the annual plan at once (no trial), the rest buy nothing
  arm weekly_trial   : P_B of users start the weekly free trial, the rest buy nothing

Arms are built from real dataset users (their transactions are kept as they are), moved out of
their original flow so the calibration, which is built from users outside the test, does not
see them. Truth at 60 days favours weekly_trial; revenue received in the first weeks favours
annual_upfront, so raw P2BB is confidently wrong.

Usage: python make_test.py <adapty-seed-data-hack>/data/offline <output folder>
"""
import csv
import gzip
import random
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SRC = Path(sys.argv[1])
DST = Path(sys.argv[2])
TEST = "AI limit: annual upfront vs weekly trial"
PLACEMENT = "ai_limit_reached"
ARM_SIZE = 3000
P_A = 0.10  # annual buyers in arm A
P_B = 0.35  # weekly trial starters in arm B
SEED = 2026


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


END = ts("2026-11-03T00:00:00Z")

with gzip.open(SRC / "users.csv.gz", "rt") as fh:
    reader = csv.DictReader(fh)
    fields = reader.fieldnames
    users = list(reader)
tx = defaultdict(list)
with gzip.open(SRC / "transactions.csv.gz", "rt") as fh:
    for t in csv.DictReader(fh):
        tx[t["user_id"]].append(t)

pools = defaultdict(list)
for u in users:
    if (END - ts(u["install_at"])).days < 60:
        continue
    rows = sorted(tx[u["user_id"]], key=lambda t: t["purchased_at"])
    if not rows:
        pools["none"].append(u)
        continue
    f = rows[0]
    if f["product"] == "annual" and f["offer"] != "free_trial":
        pools["annual_paid"].append(u)
    elif f["product"] == "weekly" and f["offer"] == "free_trial":
        pools["weekly_trial"].append(u)

rng = random.Random(SEED)
for p in pools.values():
    rng.shuffle(p)

n_a_buy, n_b_buy = round(ARM_SIZE * P_A), round(ARM_SIZE * P_B)
arm_a = pools["annual_paid"][:n_a_buy] + pools["none"][: ARM_SIZE - n_a_buy]
arm_b = pools["weekly_trial"][:n_b_buy] + pools["none"][ARM_SIZE - n_a_buy : 2 * ARM_SIZE - n_a_buy - n_b_buy]
assert len(arm_a) == ARM_SIZE and len(arm_b) == ARM_SIZE, (len(arm_a), len(arm_b))

for u in arm_a:
    u.update(ab_test=TEST, flow="annual_upfront", placement=PLACEMENT)
for u in arm_b:
    u.update(ab_test=TEST, flow="weekly_trial", placement=PLACEMENT)

DST.mkdir(parents=True, exist_ok=True)
with gzip.open(DST / "users.csv.gz", "wt", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(users)
shutil.copy(SRC / "transactions.csv.gz", DST / "transactions.csv.gz")


def rev(u, horizon):
    inst = ts(u["install_at"])
    r = 0.0
    for t in tx[u["user_id"]]:
        a = (ts(t["purchased_at"]) - inst).total_seconds() / 86400
        p = float(t["price_usd"] or 0)
        if a <= horizon:
            r += p
        if t["refunded_at"] and (ts(t["refunded_at"]) - inst).total_seconds() / 86400 <= horizon:
            r -= p
    return r


print(f"pools: annual_paid={len(pools['annual_paid'])} weekly_trial={len(pools['weekly_trial'])} none={len(pools['none'])}")
print(f"arm sizes: A={len(arm_a)} (annual buyers {n_a_buy}), B={len(arm_b)} (trial starters {n_b_buy})")
for h in (7, 14, 28, 60, 90):
    a = sum(rev(u, h) for u in arm_a) / ARM_SIZE
    b = sum(rev(u, h) for u in arm_b) / ARM_SIZE
    print(f"truth per user at {h:>2} days: annual_upfront ${a:5.2f}  weekly_trial ${b:5.2f}")
