"""Data-quality, referential-integrity, and analytical pattern validator for SFS dataset."""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from sfs.generate import (
    CHURN_CUSTOMER_IDS,
    CHURN_WINDOW_START,
    DATA_DIR,
    DEGRADING_SUPPLIERS,
    END_DATE,
    EXCURSION_ROUTE,
    LAST_QUARTER_START,
    START_DATE,
    UNDERPERFORMING_DC,
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def main() -> None:
    t0 = time.perf_counter()
    print("[sfs.validate] Starting Stark Food Services data-quality & integrity checks...\n")

    expected_tables = [
        "distribution_centers",
        "suppliers",
        "products",
        "customers",
        "customer_contacts",
        "purchase_orders",
        "po_lines",
        "accounts_payable",
        "orders",
        "order_lines",
        "shipments",
        "inventory_snapshots",
    ]

    errors: list[str] = []

    for tbl in expected_tables:
        p = DATA_DIR / f"{tbl}.jsonl"
        if not p.exists():
            errors.append(f"Missing generated file: {p}")

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    dcs = load_jsonl(DATA_DIR / "distribution_centers.jsonl")
    suppliers = load_jsonl(DATA_DIR / "suppliers.jsonl")
    products = load_jsonl(DATA_DIR / "products.jsonl")
    customers = load_jsonl(DATA_DIR / "customers.jsonl")
    contacts = load_jsonl(DATA_DIR / "customer_contacts.jsonl")
    pos = load_jsonl(DATA_DIR / "purchase_orders.jsonl")
    po_lines = load_jsonl(DATA_DIR / "po_lines.jsonl")
    ap_records = load_jsonl(DATA_DIR / "accounts_payable.jsonl")
    orders = load_jsonl(DATA_DIR / "orders.jsonl")
    order_lines = load_jsonl(DATA_DIR / "order_lines.jsonl")
    shipments = load_jsonl(DATA_DIR / "shipments.jsonl")

    # 1. Primary Key Sets & Uniqueness
    dc_ids = {r["dc_id"] for r in dcs}
    sup_ids = {r["supplier_id"] for r in suppliers}
    sku_ids = {r["sku"] for r in products}
    cust_ids = {r["customer_id"] for r in customers}
    cont_ids = {r["contact_id"] for r in contacts}
    po_ids = {r["po_id"] for r in pos}
    pol_ids = {r["po_line_id"] for r in po_lines}
    ap_ids = {r["remittance_id"] for r in ap_records}
    ord_ids = {r["order_id"] for r in orders}
    ol_ids = {r["order_line_id"] for r in order_lines}
    shp_ids = {r["shipment_id"] for r in shipments}

    pk_checks = [
        ("distribution_centers", len(dcs), len(dc_ids)),
        ("suppliers", len(suppliers), len(sup_ids)),
        ("products", len(products), len(sku_ids)),
        ("customers", len(customers), len(cust_ids)),
        ("customer_contacts", len(contacts), len(cont_ids)),
        ("purchase_orders", len(pos), len(po_ids)),
        ("po_lines", len(po_lines), len(pol_ids)),
        ("accounts_payable", len(ap_records), len(ap_ids)),
        ("orders", len(orders), len(ord_ids)),
        ("order_lines", len(order_lines), len(ol_ids)),
        ("shipments", len(shipments), len(shp_ids)),
    ]
    for name, total, unique in pk_checks:
        if total != unique:
            errors.append(f"{name}: duplicate primary keys ({total} rows vs {unique} unique PKs)")

    # Scale assertions
    if not (6 <= len(dcs) <= 8):
        errors.append(f"distribution_centers count {len(dcs)} outside 6..8 range")
    if len(products) != 600:
        errors.append(f"products count {len(products)} != 600")
    if len(customers) != 400:
        errors.append(f"customers count {len(customers)} != 400")
    if not (230_000 <= len(order_lines) <= 275_000):
        errors.append(f"order_lines count {len(order_lines)} outside ~250k target range")

    # 2. Referential Integrity Checks
    for p in products:
        if p["primary_supplier_id"] not in sup_ids:
            errors.append(f"products.primary_supplier_id orphan: {p['primary_supplier_id']}")
        if p["substitute_sku"] is not None and p["substitute_sku"] not in sku_ids:
            errors.append(f"products.substitute_sku orphan: {p['substitute_sku']}")

    for c in customers:
        if c["assigned_dc_id"] not in dc_ids:
            errors.append(f"customers.assigned_dc_id orphan: {c['assigned_dc_id']}")

    for ct in contacts:
        if ct["customer_id"] not in cust_ids:
            errors.append(f"customer_contacts.customer_id orphan: {ct['customer_id']}")

    for po in pos:
        if po["supplier_id"] not in sup_ids:
            errors.append(f"purchase_orders.supplier_id orphan: {po['supplier_id']}")
        if po["dc_id"] not in dc_ids:
            errors.append(f"purchase_orders.dc_id orphan: {po['dc_id']}")

    for pol in po_lines:
        if pol["po_id"] not in po_ids:
            errors.append(f"po_lines.po_id orphan: {pol['po_id']}")
        if pol["sku"] not in sku_ids:
            errors.append(f"po_lines.sku orphan: {pol['sku']}")

    for ap in ap_records:
        if ap["po_id"] not in po_ids:
            errors.append(f"accounts_payable.po_id orphan: {ap['po_id']}")
        if ap["supplier_id"] not in sup_ids:
            errors.append(f"accounts_payable.supplier_id orphan: {ap['supplier_id']}")

    for o in orders:
        if o["customer_id"] not in cust_ids:
            errors.append(f"orders.customer_id orphan: {o['customer_id']}")
        if o["dc_id"] not in dc_ids:
            errors.append(f"orders.dc_id orphan: {o['dc_id']}")

    for ol in order_lines:
        if ol["order_id"] not in ord_ids:
            errors.append(f"order_lines.order_id orphan: {ol['order_id']}")
        if ol["sku"] not in sku_ids:
            errors.append(f"order_lines.sku orphan: {ol['sku']}")
        if ol["fill_status"] == "SUBSTITUTED":
            if ol["substituted_sku"] is None or ol["substituted_sku"] not in sku_ids:
                errors.append(f"order_lines invalid substituted_sku on {ol['order_line_id']}")
        else:
            if ol["substituted_sku"] is not None:
                errors.append(f"order_lines unexpected substituted_sku on {ol['order_line_id']}")

    for s in shipments:
        if s["order_id"] not in ord_ids:
            errors.append(f"shipments.order_id orphan: {s['order_id']}")
        if s["dc_id"] not in dc_ids:
            errors.append(f"shipments.dc_id orphan: {s['dc_id']}")
        if s["customer_id"] not in cust_ids:
            errors.append(f"shipments.customer_id orphan: {s['customer_id']}")
        if s["load_temp_zone"] in ("refrigerated", "frozen"):
            if not isinstance(s["temperature_excursion"], bool):
                errors.append(f"shipments cold-chain missing bool temperature_excursion: {s['shipment_id']}")
        else:
            if s["temperature_excursion"] is not None:
                errors.append(f"shipments ambient load has non-null temperature_excursion: {s['shipment_id']}")

    # Stream-validate inventory_snapshots for speed and low memory
    inv_rows = 0
    inv_dc_Stockout: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    with (DATA_DIR / "inventory_snapshots.jsonl").open("r", encoding="utf-8") as f_inv:
        for line in f_inv:
            inv_rows += 1
            rec = json.loads(line)
            if rec["dc_id"] not in dc_ids or rec["sku"] not in sku_ids:
                errors.append(f"inventory_snapshots FK orphan at row {inv_rows}")
                break
            inv_dc_Stockout[rec["dc_id"]][0] += 1
            if rec["on_hand_cases"] == 0:
                inv_dc_Stockout[rec["dc_id"]][1] += 1

    expected_inv_rows = len(dcs) * len(products) * ((END_DATE - START_DATE).days + 1)
    if inv_rows != expected_inv_rows:
        errors.append(f"inventory_snapshots row count {inv_rows} != expected {expected_inv_rows}")

    # 3. Verify the 6 Analytical Patterns
    # Pattern 1: Supplier lead times in last quarter
    sup_lead_early: dict[str, list[int]] = defaultdict(list)
    sup_lead_late: dict[str, list[int]] = defaultdict(list)
    for po in pos:
        odate = dt.date.fromisoformat(po["order_date"])
        target = sup_lead_late if odate >= LAST_QUARTER_START else sup_lead_early
        target[po["supplier_id"]].append(po["actual_lead_time_days"])

    # Pattern 2: Seasonal demand by category & month
    sku_cat = {p["sku"]: p["category"] for p in products}
    ord_date_map = {o["order_id"]: dt.date.fromisoformat(o["order_date"]) for o in orders}
    ord_cust_map = {o["order_id"]: o["customer_id"] for o in orders}

    cat_month_cases: dict[tuple[str, int], int] = defaultdict(int)
    months_seen: dict[int, set[tuple[int, int]]] = defaultdict(set)
    for o in orders:
        d = ord_date_map[o["order_id"]]
        months_seen[d.month].add((d.year, d.month))

    # Pattern 6: Category fill status breakdown
    cat_status_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for ol in order_lines:
        cat = sku_cat[ol["sku"]]
        d = ord_date_map[ol["order_id"]]
        cat_month_cases[(cat, d.month)] += ol["ordered_cases"]
        cat_status_counts[cat][ol["fill_status"]] += 1
        cat_status_counts[cat]["TOTAL"] += 1

    # Pattern 3: Case fill rate by DC
    dc_ordered: dict[str, int] = defaultdict(int)
    dc_shipped: dict[str, int] = defaultdict(int)
    for o in orders:
        dc_ordered[o["dc_id"]] += o["ordered_cases"]
        dc_shipped[o["dc_id"]] += o["shipped_cases"]

    # Pattern 4: Cold-chain excursion rate by route
    route_cold_loads: dict[str, int] = defaultdict(int)
    route_excursions: dict[str, int] = defaultdict(int)
    for s in shipments:
        if s["load_temp_zone"] in ("refrigerated", "frozen"):
            route_cold_loads[s["route_id"]] += 1
            if s["temperature_excursion"]:
                route_excursions[s["route_id"]] += 1

    # Pattern 5: Churn-risk customers order volume in final 8 weeks vs prior 70 weeks
    early_weeks = (CHURN_WINDOW_START - START_DATE).days / 7.0
    late_weeks = ((END_DATE - CHURN_WINDOW_START).days + 1) / 7.0
    cust_early_cases: dict[str, int] = defaultdict(int)
    cust_late_cases: dict[str, int] = defaultdict(int)
    for o in orders:
        d = ord_date_map[o["order_id"]]
        if d >= CHURN_WINDOW_START:
            cust_late_cases[o["customer_id"]] += o["ordered_cases"]
        else:
            cust_early_cases[o["customer_id"]] += o["ordered_cases"]

    # Print comprehensive validation summary
    total_bytes = sum(p.stat().st_size for p in DATA_DIR.glob("*.jsonl"))
    print("======================================================================")
    print("1. TABLE ROW COUNTS & STORAGE FOOTPRINT")
    print("======================================================================")
    table_counts = [
        ("distribution_centers", len(dcs)),
        ("suppliers", len(suppliers)),
        ("products", len(products)),
        ("customers", len(customers)),
        ("customer_contacts", len(contacts)),
        ("purchase_orders", len(pos)),
        ("po_lines", len(po_lines)),
        ("accounts_payable", len(ap_records)),
        ("orders", len(orders)),
        ("order_lines", len(order_lines)),
        ("shipments", len(shipments)),
        ("inventory_snapshots", inv_rows),
    ]
    for tname, cnt in table_counts:
        mb = (DATA_DIR / f"{tname}.jsonl").stat().st_size / (1024 * 1024)
        print(f"  {tname:<24} : {cnt:>10,} rows  ({mb:>6.2f} MB)")
    print(f"  {'TOTAL':<24} : {sum(c for _, c in table_counts):>10,} rows  ({total_bytes / (1024 * 1024):>6.2f} MB)")

    print("\n======================================================================")
    print("2. DELIBERATE ANALYTICAL PATTERNS VERIFICATION")
    print("======================================================================")

    # Pattern 1 output
    print("\n[Pattern 1] Supplier Lead-Time Degradation (Q1-Q5 vs Final Quarter Q6):")
    for sid in sorted(DEGRADING_SUPPLIERS):
        s_obj = next(s for s in suppliers if s["supplier_id"] == sid)
        early_avg = sum(sup_lead_early[sid]) / len(sup_lead_early[sid])
        late_avg = sum(sup_lead_late[sid]) / len(sup_lead_late[sid])
        print(
            f"  - {sid} ({s_obj['name']}, contracted={s_obj['contracted_lead_time_days']}d): "
            f"Q1-Q5 avg = {early_avg:.2f}d -> Q6 avg = {late_avg:.2f}d (+{((late_avg / early_avg) - 1) * 100:.1f}%)"
        )
        if late_avg < early_avg * 2.0:
            errors.append(f"Pattern 1 failed for {sid}: {late_avg:.2f}d vs {early_avg:.2f}d")

    other_early = [v for sid, vals in sup_lead_early.items() if sid not in DEGRADING_SUPPLIERS for v in vals]
    other_late = [v for sid, vals in sup_lead_late.items() if sid not in DEGRADING_SUPPLIERS for v in vals]
    print(
        f"  - All other 40 suppliers: Q1-Q5 avg = {sum(other_early)/len(other_early):.2f}d -> "
        f"Q6 avg = {sum(other_late)/len(other_late):.2f}d"
    )

    # Pattern 2 output
    produce_summer = sum(cat_month_cases[("produce", m)] / len(months_seen[m]) for m in (6, 7, 8)) / 3.0
    produce_other = sum(cat_month_cases[("produce", m)] / len(months_seen[m]) for m in (1, 2, 3, 4, 5, 9, 10, 11, 12)) / 9.0
    protein_holiday = sum(cat_month_cases[("protein", m)] / len(months_seen[m]) for m in (11, 12)) / 2.0
    protein_other = sum(cat_month_cases[("protein", m)] / len(months_seen[m]) for m in range(1, 11)) / 10.0
    print("\n[Pattern 2] Seasonal Demand Swings (Avg Monthly Ordered Cases):")
    print(
        f"  - Produce : Summer (Jun-Aug) = {produce_summer:,.0f} cases/mo vs Non-Summer = {produce_other:,.0f} cases/mo "
        f"({produce_summer / produce_other:.2f}x lift)"
    )
    print(
        f"  - Protein : Holiday (Nov-Dec) = {protein_holiday:,.0f} cases/mo vs Non-Holiday = {protein_other:,.0f} cases/mo "
        f"({protein_holiday / protein_other:.2f}x lift)"
    )

    # Pattern 3 output
    print("\n[Pattern 3] Distribution Center Case Fill Rates:")
    for dc in dcs:
        did = dc["dc_id"]
        cfr = (dc_shipped[did] / dc_ordered[did]) * 100.0
        so_rate = (inv_dc_Stockout[did][1] / inv_dc_Stockout[did][0]) * 100.0
        marker = " <-- UNDERPERFORMING DC" if did == UNDERPERFORMING_DC else ""
        print(f"  - {did} ({dc['city']:<9}): Case Fill Rate = {cfr:5.2f}% | Snapshot Stockout Rate = {so_rate:4.2f}%{marker}")

    # Pattern 4 output
    exc_rate_404 = (route_excursions[EXCURSION_ROUTE] / route_cold_loads[EXCURSION_ROUTE]) * 100.0
    other_cold = sum(v for k, v in route_cold_loads.items() if k != EXCURSION_ROUTE)
    other_exc = sum(v for k, v in route_excursions.items() if k != EXCURSION_ROUTE)
    other_exc_rate = (other_exc / other_cold) * 100.0
    print("\n[Pattern 4] Cold-Chain Temperature Excursions (Refrigerated/Frozen Loads):")
    print(
        f"  - Route {EXCURSION_ROUTE} (Dallas DC): {route_excursions[EXCURSION_ROUTE]:,} / {route_cold_loads[EXCURSION_ROUTE]:,} "
        f"loads ({exc_rate_404:.2f}% excursion rate)"
    )
    print(
        f"  - All other 41 routes       : {other_exc:,} / {other_cold:,} "
        f"loads ({other_exc_rate:.2f}% excursion rate)"
    )

    # Pattern 5 output
    churn_early_wk = sum(cust_early_cases[c] / early_weeks for c in CHURN_CUSTOMER_IDS) / len(CHURN_CUSTOMER_IDS)
    churn_late_wk = sum(cust_late_cases[c] / late_weeks for c in CHURN_CUSTOMER_IDS) / len(CHURN_CUSTOMER_IDS)
    steady_ids = [c["customer_id"] for c in customers if c["customer_id"] not in CHURN_CUSTOMER_IDS]
    steady_early_wk = sum(cust_early_cases[c] / early_weeks for c in steady_ids) / len(steady_ids)
    steady_late_wk = sum(cust_late_cases[c] / late_weeks for c in steady_ids) / len(steady_ids)
    print("\n[Pattern 5] Customer Churn Risk (Final 8 Weeks vs Prior 70 Weeks):")
    print(
        f"  - 15 Churn-Risk Accounts : {churn_early_wk:6.1f} cases/wk -> {churn_late_wk:5.1f} cases/wk "
        f"({((churn_late_wk / churn_early_wk) - 1) * 100:.1f}% change)"
    )
    print(
        f"  - 385 Healthy Accounts   : {steady_early_wk:6.1f} cases/wk -> {steady_late_wk:5.1f} cases/wk "
        f"({((steady_late_wk / steady_early_wk) - 1) * 100:+.1f}% change)"
    )

    # Pattern 6 output
    print("\n[Pattern 6] Out-of-Stock, Partial Fill, and Substitution Rates by Category:")
    for cat in ["produce", "protein", "dairy", "frozen", "dry", "paper", "chemical"]:
        st = cat_status_counts[cat]
        tot = st["TOTAL"]
        oos_pct = (st["OUT_OF_STOCK"] / tot) * 100.0
        part_pct = (st["PARTIAL"] / tot) * 100.0
        sub_pct = (st["SUBSTITUTED"] / tot) * 100.0
        fill_pct = (st["FILLED"] / tot) * 100.0
        print(
            f"  - {cat:<10}: FILLED={fill_pct:5.2f}% | SUBSTITUTED={sub_pct:4.2f}% | "
            f"PARTIAL={part_pct:4.2f}% | OUT_OF_STOCK={oos_pct:4.2f}% (n={tot:,})"
        )

    elapsed = time.perf_counter() - t0
    if errors:
        print("\nVALIDATION FAILED:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("\n======================================================================")
    print(f"ALL DATA-QUALITY & REFERENTIAL-INTEGRITY CHECKS PASSED ({elapsed:.2f}s)")
    print("======================================================================")


if __name__ == "__main__":
    main()
