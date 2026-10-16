"""Deterministic synthetic supply-chain data generator for Stark Food Services (SFS).

Generates 18 months of daily history (2025-04-01 through 2026-09-30) across 12 tables
in newline-delimited JSON (.jsonl) under data/, matching sql/schema.sql.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import time
from pathlib import Path
from typing import Any

SEED = 42
START_DATE = dt.date(2025, 4, 1)
END_DATE = dt.date(2026, 9, 30)  # 548 days (18 months)
LAST_QUARTER_START = dt.date(2026, 7, 1)
CHURN_WINDOW_START = dt.date(2026, 8, 6)  # Final 8 weeks (56 days)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# Deliberate pattern constants (documented in README.md)
DEGRADING_SUPPLIERS = {"SUP-002", "SUP-008"}
UNDERPERFORMING_DC = "DC-SE-01"
EXCURSION_ROUTE = "RTE-SW-404"
CHURN_CUSTOMER_IDS = {
    "CUST-0015",
    "CUST-0042",
    "CUST-0068",
    "CUST-0095",
    "CUST-0122",
    "CUST-0149",
    "CUST-0176",
    "CUST-0203",
    "CUST-0230",
    "CUST-0257",
    "CUST-0284",
    "CUST-0311",
    "CUST-0338",
    "CUST-0365",
    "CUST-0392",
}

# Category definitions: (sku_count, temp_zone_weights, shelf_life_range, cost_range, margin_range)
CATEGORY_SPECS: dict[str, dict[str, Any]] = {
    "produce": {
        "count": 95,
        "temp_zones": [("refrigerated", 1.0)],
        "shelf_life": (7, 21),
        "cost": (18.0, 58.0),
        "pack_sizes": ["1/24 ct", "1/50 lb", "4/5 lb", "6/2 lb", "1/30 lb", "2/10 lb"],
        "brands": ["SunCoast Harvest", "Valley Greens", "Stark Culinary Fresh", "Salinas Gold"],
        "items": [
            "Romaine Hearts", "Baby Spinach Washed", "Russet Potatoes 70ct", "Yellow Onions Jumbo",
            "Roma Tomatoes", "Hass Avocados 48ct", "Red Bell Peppers", "Seedless Lemons",
            "Chopped Iceberg Blend", "Whole Carrots", "Broccoli Florets", "Fresh Strawberries",
            "Green Asparagus Spears", "English Cucumbers", "Crimini Mushrooms", "Fresh Basil Bunches",
            "Diced Celery", "Red Cabbage Shredded", "Sweet Corn Ears", "Honeydew Melons",
        ],
        # Baseline line fulfillment rates: (oos_prob, partial_prob, sub_prob)
        "fill_rates": (0.024, 0.034, 0.054),
    },
    "protein": {
        "count": 105,
        "temp_zones": [("refrigerated", 0.62), ("frozen", 0.38)],
        "shelf_life": (12, 28),  # overridden for frozen to (180, 365)
        "cost": (68.0, 240.0),
        "pack_sizes": ["4/10 lb", "2/15 lb", "1/40 lb", "8/5 lb", "12/12 oz", "20/8 oz"],
        "brands": ["Heartland Prime", "Stark Butcher Reserve", "Prairie Gold", "Mariners Catch"],
        "items": [
            "USDA Choice Ribeye Roll", "Boneless Skinless Chicken Breast", "80/20 Ground Beef Chuck",
            "Applewood Smoked Bacon", "Pork Tenderloin Center Cut", "Atlantic Salmon Portions",
            "Jumbo White Shrimp 16/20", "Oven Roasted Turkey Breast", "USDA Choice Striploin",
            "Chicken Wings Jumbo Party", "Smoked Andouille Sausage", "Beef Short Ribs Bone-In",
            "IQF Cod Loins", "Sliced Pepperoni", "Ground Pork Bulk", "Prime Brisket Flat",
            "Lamb Rack Frenched", "Halibut Fillets", "Breaded Chicken Tenders", "Italian Meatballs",
        ],
        "fill_rates": (0.017, 0.025, 0.034),
    },
    "dairy": {
        "count": 75,
        "temp_zones": [("refrigerated", 1.0)],
        "shelf_life": (14, 60),
        "cost": (24.0, 88.0),
        "pack_sizes": ["4/1 gal", "6/5 lb", "36/1 doz", "4/5 lb", "12/1 qt", "1/30 lb"],
        "brands": ["MeadowGold Dairy", "Stark Creamery", "Wisconsin Heritage", "Cloverland Farms"],
        "items": [
            "Whole Milk Vitamin D", "Heavy Whipping Cream 36%", "Unsalted Sweet Cream Butter",
            "Shredded Low-Moisture Mozzarella", "Sharp Cheddar Block", "Large Grade AA Shell Eggs",
            "Liquid Whole Eggs", "Plain Greek Yogurt", "Cultured Sour Cream", "Grated Parmesan Reggiano",
            "Sliced Swiss Cheese", "Buttermilk Cultured", "Cream Cheese Loaf", "Provolone Sliced",
            "Half & Half Ultra-Pasteurized",
        ],
        "fill_rates": (0.013, 0.019, 0.044),
    },
    "dry": {
        "count": 130,
        "temp_zones": [("ambient", 1.0)],
        "shelf_life": (180, 730),
        "cost": (16.0, 74.0),
        "pack_sizes": ["6/#10 can", "1/50 lb", "4/1 gal", "12/2 lb", "2/25 lb", "6/5 lb"],
        "brands": ["Stark Pantry Essentials", "Pacific Hearth", "Golden Mill", "San Marzano Select"],
        "items": [
            "Crushed Tomatoes in Puree", "Extra Virgin Olive Oil Blend", "All-Purpose Enriched Flour",
            "Long Grain Parboiled Rice", "Canola Frying Shortening", "Penne Rigate Pasta",
            "Kosher Flake Salt", "Granulated Cane Sugar", "Classic Mayonnaise Heavy Duty",
            "Dijon Mustard Bulk", "Black Beans Fancy", "Balsamic Vinegar of Modena",
            "Panko Bread Crumbs", "Pure Vanilla Extract", "Cracked Black Pepper",
            "Clam Juice Base", "Roasted Chicken Base", "Ketchup #10 Can", "Rolled Oats", "Cornstarch",
        ],
        "fill_rates": (0.006, 0.010, 0.021),
    },
    "frozen": {
        "count": 95,
        "temp_zones": [("frozen", 1.0)],
        "shelf_life": (180, 540),
        "cost": (26.0, 95.0),
        "pack_sizes": ["6/5 lb", "4/6 lb", "24/8 oz", "1/30 lb", "12/2.5 lb", "72/4 oz"],
        "brands": ["Arctic Peak", "Stark Bakehouse", "Northwest Potato Co", "SweetStreet Culinary"],
        "items": [
            "Shoestring French Fries 3/8", "Sweet Potato Waffle Fries", "Brioche Hamburger Buns",
            "Par-Baked Artisan Sourdough", "IQF Sweet Green Peas", "IQF Mixed Berries",
            "New York Style Cheesecake", "Chocolate Lava Cakes", "Battered Onion Rings",
            "Mozzarella Cheese Sticks", "Croissant Dough Sheeted", "IQF Edamame Shelled",
            "Hashbrown Patties Oval", "Mini Churros", "Vegetable Spring Rolls",
        ],
        "fill_rates": (0.009, 0.014, 0.027),
    },
    "paper": {
        "count": 60,
        "temp_zones": [("ambient", 1.0)],
        "shelf_life": (1095, 1825),
        "cost": (22.0, 68.0),
        "pack_sizes": ["1/500 ct", "4/250 ct", "10/100 ct", "1/1000 ft", "20/50 ct", "12/100 ct"],
        "brands": ["TuffWrap Disposables", "Stark EcoPack", "ClearShield", "DuraFold"],
        "items": [
            "Heavy Duty Aluminum Foil 18in", "Foodservice Film Wrap 2000ft", "Compostable Clamshell 9x9",
            "Kraft Takeout Shopping Bags", "2-Ply Beverage Napkins", "Pleated Souffle Portion Cups",
            "Nitrile Powder-Free Gloves L", "Nitrile Powder-Free Gloves M", "Insulated Hot Cups 16oz",
            "Polypropylene Cold Cups 20oz", "Deli Interfolded Wax Paper", "Centerpull Paper Towels",
        ],
        "fill_rates": (0.004, 0.008, 0.029),
    },
    "chemical": {
        "count": 40,
        "temp_zones": [("ambient", 1.0)],
        "shelf_life": (730, 1095),
        "cost": (34.0, 115.0),
        "pack_sizes": ["4/1 gal", "2/2.5 gal", "1/5 gal", "6/32 oz", "4/2 L"],
        "brands": ["SanitiPro Systems", "Stark CleanGuard", "HydroPure Commercial"],
        "items": [
            "High-Temp Dishmachine Detergent", "Low-Temp Chlorine Sanitizer", "Quaternary Surface Sanitizer",
            "Heavy Duty Grill & Oven Degreaser", "Rinse Aid Drying Agent", "Foaming Antibacterial Hand Soap",
            "Stainless Steel Polish Spray", "Delimer Scale Remover", "Pot & Pan Manual Detergent",
            "Floor Quarry Tile Cleaner",
        ],
        # Chemical dispensers are proprietary: very low OOS and virtually zero substitution
        "fill_rates": (0.004, 0.006, 0.002),
    },
}


def build_distribution_centers() -> list[dict[str, Any]]:
    return [
        {
            "dc_id": "DC-NE-01",
            "name": "SFS Northeast Metro DC",
            "city": "Newark",
            "state": "NJ",
            "region": "Northeast",
            "capacity_cases": 310000,
            "cold_storage_capacity_cases": 135000,
        },
        {
            "dc_id": "DC-MA-01",
            "name": "SFS Mid-Atlantic Chesapeake DC",
            "city": "Baltimore",
            "state": "MD",
            "region": "Mid-Atlantic",
            "capacity_cases": 240000,
            "cold_storage_capacity_cases": 105000,
        },
        {
            "dc_id": "DC-SE-01",
            "name": "SFS Southeast Hub DC",
            "city": "Atlanta",
            "state": "GA",
            "region": "Southeast",
            "capacity_cases": 265000,
            "cold_storage_capacity_cases": 98000,
        },
        {
            "dc_id": "DC-MW-01",
            "name": "SFS Midwest Great Lakes DC",
            "city": "Chicago",
            "state": "IL",
            "region": "Midwest",
            "capacity_cases": 295000,
            "cold_storage_capacity_cases": 130000,
        },
        {
            "dc_id": "DC-SW-01",
            "name": "SFS Southwest Lone Star DC",
            "city": "Dallas",
            "state": "TX",
            "region": "Southwest",
            "capacity_cases": 280000,
            "cold_storage_capacity_cases": 122000,
        },
        {
            "dc_id": "DC-WE-01",
            "name": "SFS West Coast Inland Empire DC",
            "city": "Ontario",
            "state": "CA",
            "region": "West",
            "capacity_cases": 325000,
            "cold_storage_capacity_cases": 145000,
        },
        {
            "dc_id": "DC-NW-01",
            "name": "SFS Pacific Northwest Puget DC",
            "city": "Seattle",
            "state": "WA",
            "region": "Pacific Northwest",
            "capacity_cases": 215000,
            "cold_storage_capacity_cases": 95000,
        },
    ]


def build_suppliers(rng: random.Random) -> list[dict[str, Any]]:
    regions = [
        "Northeast", "Mid-Atlantic", "Southeast", "Midwest",
        "Southwest", "West", "Pacific Northwest",
    ]
    categories = list(CATEGORY_SPECS.keys())
    supplier_prefixes = [
        "Apex", "BlueRidge", "Cascade", "Delta", "Emerald", "Frontier",
        "GoldenState", "Heritage", "Imperial", "Keystone", "Liberty", "Meridian",
        "Noble", "Olympic", "Pinnacle", "Redwood", "Sierra", "Summit",
        "Timberline", "United", "Vanguard", "Western",
    ]
    supplier_suffixes = {
        "produce": ["Fresh Growers", "Farms Co-op", "Valley Produce", "AgriPartners"],
        "protein": ["Prime Meats", "Packing Co.", "Poultry & Beef", "Seafoods"],
        "dairy": ["Creamery", "Dairy Foods", "Cheese Collective", "Farms"],
        "dry": ["Milling & Provisions", "Specialty Foods", "Culinary Imports", "Canners"],
        "frozen": ["Frozen Foods", "Cold Kitchens", "Bakery & Frozen", "IQF Specialties"],
        "paper": ["Packaging Corp", "Foodservice Disposables", "Paper & Film", "Ecoware"],
        "chemical": ["Sanitation Systems", "Hygiene Labs", "Chemical Solutions", "CleanTech"],
    }

    suppliers: list[dict[str, Any]] = []
    idx = 1
    for cat in categories:
        for i in range(6):
            sup_id = f"SUP-{idx:03d}"
            # Explicit naming for the two intentional degrading suppliers
            if sup_id == "SUP-002":
                name = "SunCoast Fresh Growers"
                region = "Southeast"
                contracted = 3
                profile = "degrading_last_quarter"
                on_time = 0.94
            elif sup_id == "SUP-008":
                name = "Heartland Prime Meats"
                region = "Midwest"
                contracted = 4
                profile = "degrading_last_quarter"
                on_time = 0.95
            else:
                prefix = supplier_prefixes[(idx * 3 + i) % len(supplier_prefixes)]
                suffix = supplier_suffixes[cat][i % len(supplier_suffixes[cat])]
                name = f"{prefix} {suffix}"
                region = regions[(idx + i) % len(regions)]
                if cat in ("produce", "dairy"):
                    contracted = rng.randint(2, 5)
                elif cat == "protein":
                    contracted = rng.randint(3, 6)
                else:
                    contracted = rng.randint(4, 9)
                profile = rng.choices(
                    ["tier_1_reliable", "standard", "variable"],
                    weights=[0.50, 0.35, 0.15],
                    k=1,
                )[0]
                if profile == "tier_1_reliable":
                    on_time = round(rng.uniform(0.95, 0.98), 3)
                elif profile == "standard":
                    on_time = round(rng.uniform(0.90, 0.94), 3)
                else:
                    on_time = round(rng.uniform(0.84, 0.89), 3)

            suppliers.append(
                {
                    "supplier_id": sup_id,
                    "name": name,
                    "region": region,
                    "primary_category": cat,
                    "contracted_lead_time_days": contracted,
                    "reliability_profile": profile,
                    "baseline_on_time_rate": on_time,
                }
            )
            idx += 1
    return suppliers


def build_products(
    rng: random.Random, suppliers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    suppliers_by_cat: dict[str, list[str]] = {}
    for s in suppliers:
        suppliers_by_cat.setdefault(s["primary_category"], []).append(s["supplier_id"])

    products: list[dict[str, Any]] = []
    sku_num = 10001
    skus_by_cat_zone: dict[tuple[str, str], list[str]] = {}

    for cat, spec in CATEGORY_SPECS.items():
        count = spec["count"]
        tz_choices = [tz for tz, _ in spec["temp_zones"]]
        tz_weights = [w for _, w in spec["temp_zones"]]
        cat_suppliers = suppliers_by_cat[cat]
        items = spec["items"]
        brands = spec["brands"]
        pack_sizes = spec["pack_sizes"]

        for i in range(count):
            sku = f"SKU-{sku_num}"
            sku_num += 1
            temp_zone = rng.choices(tz_choices, weights=tz_weights, k=1)[0]
            if cat == "protein" and temp_zone == "frozen":
                shelf_life = rng.randint(180, 365)
            else:
                shelf_life = rng.randint(*spec["shelf_life"])

            base_item = items[i % len(items)]
            variant_num = (i // len(items)) + 1
            grade_tags = ["Select", "Foodservice Pack", "Chef Cut", "Bulk", "Premium", "Classic"]
            grade = grade_tags[(i + variant_num) % len(grade_tags)]
            pack_size = pack_sizes[i % len(pack_sizes)]
            brand = brands[i % len(brands)]
            description = f"{brand} {base_item} ({grade}, {pack_size})"

            case_cost = round(rng.uniform(*spec["cost"]), 2)
            # Distributor gross margin 16% - 28%
            list_price = round(case_cost * rng.uniform(1.18, 1.32), 2)
            primary_supplier_id = cat_suppliers[i % len(cat_suppliers)]

            prod = {
                "sku": sku,
                "description": description,
                "category": cat,
                "brand": brand,
                "pack_size": pack_size,
                "case_cost": case_cost,
                "list_price": list_price,
                "temp_zone": temp_zone,
                "shelf_life_days": shelf_life,
                "primary_supplier_id": primary_supplier_id,
                "substitute_sku": None,
            }
            products.append(prod)
            skus_by_cat_zone.setdefault((cat, temp_zone), []).append(sku)

    # Link realistic substitute_sku within same (category, temp_zone)
    for prod in products:
        peers = skus_by_cat_zone[(prod["category"], prod["temp_zone"])]
        if len(peers) > 1:
            idx = peers.index(prod["sku"])
            prod["substitute_sku"] = peers[(idx + 1) % len(peers)]

    return products


def build_customers_and_contacts(
    rng: random.Random, dcs: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    segments = ["restaurant", "healthcare", "education", "hospitality"]
    seg_weights = [0.46, 0.18, 0.16, 0.20]

    seg_names = {
        "restaurant": [
            "Harbor Grill", "Oak & Ember Bistro", "Bella Notte Trattoria", "Copper Kettle Diner",
            "Mesa Verde Cantina", "Golden Dragon Kitchen", "Prime Cut Steakhouse", "Bluefin Sushi & Bar",
            "Magnolia Southern Table", "Ironworks Gastropub", "Rustic Vine Brasserie", "Seaside Chowder House",
        ],
        "healthcare": [
            "St. Jude Regional Medical Center", "Mercy General Hospital", "Pinecrest Senior Living",
            "Valley View Rehabilitation", "Metro Health Pavilion", "Sunrise Assisted Care",
            "Cedar Sinai Outpatient Culinary", "Oakwood Memorial Hospital",
        ],
        "education": [
            "Westfield Unified School District", "Northgate State University Dining",
            "Lincoln County Public Schools", "St. Xavier Preparatory Academy",
            "Redwood Community College", "Lakeview Charter Schools",
        ],
        "hospitality": [
            "Grand Regency Hotel & Conference", "Mariner Bay Resort & Spa",
            "Summit Peak Lodge", "Crown Plaza Convention Center",
            "Bayside Boutique Hotel", "Starlight Casino & Resort",
        ],
    }

    first_names = [
        "Elena", "Marcus", "David", "Sarah", "Carlos", "Priya", "James", "Hannah",
        "Devon", "Mei", "Anthony", "Rachel", "Omar", "Lauren", "Gabriel", "Nina",
        "mateso", "Victor", "claire", "Tomas", "Nadia", "kenji", "Avery", "Monica",
    ]
    first_names = [n.capitalize() for n in first_names]
    last_names = [
        "Reyes", "Chen", "Patel", "O'Connor", "Kowalski", "Rivera", "Brooks", "Kim",
        "Bauer", "Morales", "Jenkins", "Sullivan", "Gupta", "Rossi", "Gomez", "Price",
        "Bennett", "Foster", "Alvarez", "Mercer", "Nguyen", "Bell", "Ward", "Torres",
    ]
    roles = [
        "Executive Chef", "Director of Purchasing", "Kitchen Manager",
        "Food & Beverage Director", "Accounts Payable Lead", "General Manager",
    ]
    area_codes = {
        "Northeast": "201",
        "Mid-Atlantic": "410",
        "Southeast": "404",
        "Midwest": "312",
        "Southwest": "214",
        "West": "909",
        "Pacific Northwest": "206",
    }

    customers: list[dict[str, Any]] = []
    contacts: list[dict[str, Any]] = []
    contact_seq = 1

    # Distribute 400 customers across the 7 DCs
    for i in range(1, 401):
        cust_id = f"CUST-{i:04d}"
        dc = dcs[(i - 1) % len(dcs)]
        segment = rng.choices(segments, weights=seg_weights, k=1)[0]
        base_name = seg_names[segment][(i - 1) % len(seg_names[segment])]
        operator_name = f"{base_name} #{(i // len(seg_names[segment])) + 1} ({dc['city']})"

        credit_terms = rng.choices(
            ["Net 30", "Net 15", "Net 45", "COD"],
            weights=[0.55, 0.25, 0.15, 0.05],
            k=1,
        )[0]
        open_offset = rng.randint(60, 1800)
        account_open_date = (START_DATE - dt.timedelta(days=open_offset)).isoformat()

        customers.append(
            {
                "customer_id": cust_id,
                "operator_name": operator_name,
                "segment": segment,
                "region": dc["region"],
                "credit_terms": credit_terms,
                "assigned_dc_id": dc["dc_id"],
                "account_open_date": account_open_date,
            }
        )

        # Generate 1 to 3 PII contacts per customer
        num_contacts = rng.choices([1, 2, 3], weights=[0.30, 0.50, 0.20], k=1)[0]
        domain_slug = (
            base_name.lower()
            .replace("&", "and")
            .replace(".", "")
            .replace("'", "")
            .replace(" ", "")
        )
        area = area_codes[dc["region"]]
        for c_idx in range(num_contacts):
            fname = rng.choice(first_names)
            lname = rng.choice(last_names)
            full_name = f"{fname} {lname}"
            email = f"{fname.lower()}.{lname.lower()}{i}@accounts.{domain_slug}.com"
            phone = f"+1-{area}-555-{rng.randint(1000, 9999):04d}"
            role = roles[c_idx % len(roles)]
            contacts.append(
                {
                    "contact_id": f"CONT-{contact_seq:05d}",
                    "customer_id": cust_id,
                    "name": full_name,
                    "email": email,
                    "phone": phone,
                    "role": role,
                    "is_primary": c_idx == 0,
                }
            )
            contact_seq += 1

    return customers, contacts


def build_po_and_ap(
    rng: random.Random,
    dcs: list[dict[str, Any]],
    suppliers: list[dict[str, Any]],
    products: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    products_by_supplier: dict[str, list[dict[str, Any]]] = {}
    for p in products:
        products_by_supplier.setdefault(p["primary_supplier_id"], []).append(p)

    # Pre-assign deterministic sensitive banking details per supplier for AP table
    banks = [
        ("JPMorgan Chase Bank", "021000021"),
        ("Bank of America", "026009593"),
        ("Wells Fargo Bank", "121000248"),
        ("Citibank N.A.", "021000089"),
        ("U.S. Bank N.A.", "091000022"),
        ("PNC Bank", "043000096"),
        ("Truist Bank", "061000104"),
    ]
    supplier_banking: dict[str, dict[str, str]] = {}
    for idx, sup in enumerate(suppliers):
        bank_name, routing = banks[idx % len(banks)]
        acct_num = f"{rng.randint(1000000000, 9999999999)}"
        ein = f"{rng.randint(10, 99)}-{rng.randint(1000000, 9999999)}"
        slug = sup["name"].lower().replace(" ", "").replace("&", "").replace(".", "")
        supplier_banking[sup["supplier_id"]] = {
            "bank_name": bank_name,
            "aba_routing_number": routing,
            "bank_account_number": acct_num,
            "supplier_tax_id": ein,
            "remittance_email": f"remittance@{slug}.com",
            "payment_method": rng.choices(["ACH", "EFT", "WIRE"], weights=[0.65, 0.25, 0.10], k=1)[0],
        }

    purchase_orders: list[dict[str, Any]] = []
    po_lines: list[dict[str, Any]] = []
    accounts_payable: list[dict[str, Any]] = []

    po_seq = 1
    pol_seq = 1
    ap_seq = 1

    total_days = (END_DATE - START_DATE).days + 1
    # Issue replenishment POs every week across DCs and suppliers
    for day_offset in range(0, total_days, 7):
        base_date = START_DATE + dt.timedelta(days=day_offset)
        for dc in dcs:
            # Each week, a DC places POs with ~16 suppliers
            sampled_suppliers = rng.sample(suppliers, k=16)
            # Ensure degrading suppliers SUP-002 and SUP-008 are regularly ordered so pattern is rich
            for must_id in DEGRADING_SUPPLIERS:
                if not any(s["supplier_id"] == must_id for s in sampled_suppliers):
                    for s in suppliers:
                        if s["supplier_id"] == must_id:
                            sampled_suppliers[0] = s
                            break

            for sup in sampled_suppliers:
                sup_id = sup["supplier_id"]
                order_date = base_date + dt.timedelta(days=rng.randint(0, 4))
                if order_date > END_DATE:
                    order_date = END_DATE

                contracted = sup["contracted_lead_time_days"]

                # PATTERN 1: Two suppliers (SUP-002, SUP-008) whose lead times degrade badly in the last quarter
                if sup_id in DEGRADING_SUPPLIERS and order_date >= LAST_QUARTER_START:
                    if order_date.month == 7:
                        delay = rng.randint(4, 7)
                    elif order_date.month == 8:
                        delay = rng.randint(7, 10)
                    else:
                        delay = rng.randint(10, 14)
                    actual_lead = contracted + delay
                else:
                    if rng.random() < sup["baseline_on_time_rate"]:
                        actual_lead = max(1, contracted + rng.choice([-1, 0, 0, 0, 1]))
                    else:
                        actual_lead = contracted + rng.randint(2, 4)

                expected_deliv = order_date + dt.timedelta(days=contracted)
                actual_deliv = order_date + dt.timedelta(days=actual_lead)

                sup_skus = products_by_supplier[sup_id]
                num_lines = min(len(sup_skus), rng.randint(3, 6))
                chosen_skus = rng.sample(sup_skus, k=num_lines)

                po_id = f"PO-{po_seq:06d}"
                po_seq += 1

                tot_ordered = 0
                tot_received = 0
                tot_cost = 0.0

                for line_no, prod in enumerate(chosen_skus, start=1):
                    cat = prod["category"]
                    seasonal_mult = 1.0
                    if cat == "produce" and order_date.month in (6, 7, 8):
                        seasonal_mult = 1.65
                    elif cat == "protein" and order_date.month in (11, 12):
                        seasonal_mult = 1.75

                    ordered_cases = int(round(rng.randint(40, 140) * seasonal_mult))
                    if sup_id in DEGRADING_SUPPLIERS and order_date >= LAST_QUARTER_START:
                        # Degrading suppliers also short-ship some replenishment lines
                        received_cases = int(round(ordered_cases * rng.uniform(0.72, 0.92)))
                    elif dc["dc_id"] == UNDERPERFORMING_DC and rng.random() < 0.25:
                        received_cases = int(round(ordered_cases * rng.uniform(0.80, 0.94)))
                    else:
                        received_cases = ordered_cases if rng.random() < 0.94 else int(round(ordered_cases * rng.uniform(0.88, 0.98)))

                    cost = prod["case_cost"]
                    line_cost = round(received_cases * cost, 2)

                    po_lines.append(
                        {
                            "po_line_id": f"POL-{pol_seq:07d}",
                            "po_id": po_id,
                            "line_number": line_no,
                            "sku": prod["sku"],
                            "ordered_cases": ordered_cases,
                            "received_cases": received_cases,
                            "case_cost": cost,
                            "line_cost": line_cost,
                        }
                    )
                    pol_seq += 1
                    tot_ordered += ordered_cases
                    tot_received += received_cases
                    tot_cost += line_cost

                tot_cost = round(tot_cost, 2)
                if actual_lead > contracted + 1:
                    status = "LATE_RECEIVED"
                elif tot_received < tot_ordered:
                    status = "PARTIAL"
                else:
                    status = "RECEIVED"

                purchase_orders.append(
                    {
                        "po_id": po_id,
                        "supplier_id": sup_id,
                        "dc_id": dc["dc_id"],
                        "order_date": order_date.isoformat(),
                        "expected_delivery_date": expected_deliv.isoformat(),
                        "actual_delivery_date": actual_deliv.isoformat(),
                        "contracted_lead_time_days": contracted,
                        "actual_lead_time_days": actual_lead,
                        "status": status,
                        "total_ordered_cases": tot_ordered,
                        "total_received_cases": tot_received,
                        "total_cost": tot_cost,
                    }
                )

                bank_info = supplier_banking[sup_id]
                pay_date = actual_deliv + dt.timedelta(days=rng.choice([15, 30]))
                accounts_payable.append(
                    {
                        "remittance_id": f"AP-{ap_seq:06d}",
                        "po_id": po_id,
                        "supplier_id": sup_id,
                        "invoice_number": f"INV-{sup_id[-3:]}-{po_seq:06d}",
                        "invoice_date": actual_deliv.isoformat(),
                        "payment_date": pay_date.isoformat(),
                        "payment_amount": tot_cost,
                        "payment_method": bank_info["payment_method"],
                        "bank_name": bank_info["bank_name"],
                        "aba_routing_number": bank_info["aba_routing_number"],
                        "bank_account_number": bank_info["bank_account_number"],
                        "supplier_tax_id": bank_info["supplier_tax_id"],
                        "remittance_email": bank_info["remittance_email"],
                    }
                )
                ap_seq += 1

    return purchase_orders, po_lines, accounts_payable


def generate_orders_lines_shipments(
    rng: random.Random,
    dcs: list[dict[str, Any]],
    customers: list[dict[str, Any]],
    products: list[dict[str, Any]],
    orders_path: Path,
    order_lines_path: Path,
    shipments_path: Path,
) -> dict[str, int]:
    """Stream-generate orders, order_lines (~250k rows), and shipments directly to disk."""
    products_by_cat: dict[str, list[dict[str, Any]]] = {}
    product_map: dict[str, dict[str, Any]] = {}
    for p in products:
        products_by_cat.setdefault(p["category"], []).append(p)
        product_map[p["sku"]] = p

    # Define 6 routes per DC; ensure RTE-SW-404 is in DC-SW-01
    dc_routes: dict[str, list[str]] = {
        "DC-NE-01": [f"RTE-NE-10{i}" for i in range(1, 7)],
        "DC-MA-01": [f"RTE-MA-20{i}" for i in range(1, 7)],
        "DC-SE-01": [f"RTE-SE-30{i}" for i in range(1, 7)],
        "DC-SW-01": [f"RTE-SW-40{i}" for i in range(1, 7)],  # includes RTE-SW-404
        "DC-MW-01": [f"RTE-MW-50{i}" for i in range(1, 7)],
        "DC-WE-01": [f"RTE-WE-60{i}" for i in range(1, 7)],
        "DC-NW-01": [f"RTE-NW-70{i}" for i in range(1, 7)],
    }

    # Assign each customer a primary route on their assigned DC and a baseline ordering probability
    cust_route: dict[str, str] = {}
    cust_daily_order_prob: dict[str, float] = {}
    for idx, c in enumerate(customers):
        cid = c["customer_id"]
        routes = dc_routes[c["assigned_dc_id"]]
        cust_route[cid] = routes[idx % len(routes)]
        if cid in CHURN_CUSTOMER_IDS:
            # High, steady ordering cadence before the final 8-week churn drop
            cust_daily_order_prob[cid] = 0.285
        else:
            # Calibrated so 400 customers x 548 days x ~6.0 lines/order ~= 251,000 order lines
            cust_daily_order_prob[cid] = round(rng.uniform(0.160, 0.235), 4)

    categories = list(CATEGORY_SPECS.keys())
    base_cat_weights = {
        "produce": 0.20,
        "protein": 0.19,
        "dairy": 0.15,
        "dry": 0.21,
        "frozen": 0.14,
        "paper": 0.07,
        "chemical": 0.04,
    }

    order_seq = 1
    ol_seq = 1
    shp_seq = 1
    total_days = (END_DATE - START_DATE).days + 1

    with (
        orders_path.open("w", encoding="utf-8") as f_ord,
        order_lines_path.open("w", encoding="utf-8") as f_ol,
        shipments_path.open("w", encoding="utf-8") as f_shp,
    ):
        ord_buf: list[str] = []
        ol_buf: list[str] = []
        shp_buf: list[str] = []

        for day_idx in range(total_days):
            cur_date = START_DATE + dt.timedelta(days=day_idx)
            date_str = cur_date.isoformat()
            month = cur_date.month
            weekday = cur_date.weekday()

            # Lower order placement on Sundays
            dow_factor = 0.45 if weekday == 6 else (1.08 if weekday in (0, 3) else 1.0)

            # PATTERN 2: Seasonal category demand weights (produce in summer, protein around holidays)
            cat_w = dict(base_cat_weights)
            produce_qty_mult = 1.0
            protein_qty_mult = 1.0
            if month in (6, 7, 8):
                cat_w["produce"] *= 1.55
                produce_qty_mult = 1.70
            elif month in (11, 12):
                cat_w["protein"] *= 1.60
                protein_qty_mult = 1.80
            elif month in (1, 2):
                produce_qty_mult = 0.85

            cat_weight_list = [cat_w[c] for c in categories]

            for cust in customers:
                cid = cust["customer_id"]
                prob = cust_daily_order_prob[cid] * dow_factor

                # PATTERN 5: ~15 customers whose order volume drops sharply in the final 8 weeks
                is_churn_window = cid in CHURN_CUSTOMER_IDS and cur_date >= CHURN_WINDOW_START
                if is_churn_window:
                    prob *= 0.22  # ~78% drop in order frequency

                if rng.random() >= prob:
                    continue

                dc_id = cust["assigned_dc_id"]
                order_id = f"ORD-{order_seq:07d}"
                order_seq += 1
                sched_deliv_date = cur_date + dt.timedelta(days=1 if rng.random() < 0.80 else 2)

                if is_churn_window:
                    num_lines = rng.randint(2, 4)
                elif cid in CHURN_CUSTOMER_IDS:
                    num_lines = rng.randint(6, 9)
                else:
                    num_lines = rng.randint(3, 9)

                chosen_cats = rng.choices(categories, weights=cat_weight_list, k=num_lines)
                used_skus: set[str] = set()
                order_skus: list[dict[str, Any]] = []
                for cat in chosen_cats:
                    pool = products_by_cat[cat]
                    for _ in range(5):
                        cand = pool[rng.randrange(len(pool))]
                        if cand["sku"] not in used_skus:
                            used_skus.add(cand["sku"])
                            order_skus.append(cand)
                            break

                tot_ordered_cases = 0
                tot_shipped_cases = 0
                order_total = 0.0
                has_frozen = False
                has_refrigerated = False

                for line_no, prod in enumerate(order_skus, start=1):
                    cat = prod["category"]
                    base_cases = rng.randint(3, 18)
                    if is_churn_window:
                        base_cases = max(1, int(round(base_cases * 0.45)))
                    elif cid in CHURN_CUSTOMER_IDS:
                        base_cases = rng.randint(10, 22)

                    if cat == "produce":
                        ordered_cases = max(1, int(round(base_cases * produce_qty_mult)))
                    elif cat == "protein":
                        ordered_cases = max(1, int(round(base_cases * protein_qty_mult)))
                    else:
                        ordered_cases = base_cases

                    # PATTERN 3 & PATTERN 6: Category-specific OOS/partial/substitution + DC-SE-01 worse fill rate
                    oos_p, part_p, sub_p = CATEGORY_SPECS[cat]["fill_rates"]
                    if dc_id == UNDERPERFORMING_DC:
                        # Materially worse case fill rate at DC-SE-01 (~84.3% vs ~97.1% at other DCs)
                        oos_p = min(0.25, oos_p * 5.8)
                        part_p = min(0.30, part_p * 5.2)

                    roll = rng.random()
                    substituted_sku = None
                    unit_price = prod["list_price"]

                    if roll < oos_p:
                        fill_status = "OUT_OF_STOCK"
                        shipped_cases = 0
                    elif roll < oos_p + part_p:
                        fill_status = "PARTIAL"
                        fill_frac = rng.uniform(0.30, 0.55) if dc_id == UNDERPERFORMING_DC else rng.uniform(0.50, 0.78)
                        shipped_cases = max(1, min(ordered_cases - 1, int(round(ordered_cases * fill_frac))))
                        if ordered_cases == 1:
                            fill_status = "OUT_OF_STOCK"
                            shipped_cases = 0
                    elif roll < oos_p + part_p + sub_p and prod["substitute_sku"] is not None:
                        fill_status = "SUBSTITUTED"
                        shipped_cases = ordered_cases
                        substituted_sku = prod["substitute_sku"]
                        unit_price = product_map[substituted_sku]["list_price"]
                    else:
                        fill_status = "FILLED"
                        shipped_cases = ordered_cases

                    line_total = round(shipped_cases * unit_price, 2)
                    tot_ordered_cases += ordered_cases
                    tot_shipped_cases += shipped_cases
                    order_total += line_total

                    if shipped_cases > 0:
                        tz = prod["temp_zone"]
                        if tz == "frozen":
                            has_frozen = True
                        elif tz == "refrigerated":
                            has_refrigerated = True

                    ol_buf.append(
                        json.dumps(
                            {
                                "order_line_id": f"OL-{ol_seq:07d}",
                                "order_id": order_id,
                                "line_number": line_no,
                                "sku": prod["sku"],
                                "ordered_cases": ordered_cases,
                                "shipped_cases": shipped_cases,
                                "fill_status": fill_status,
                                "substituted_sku": substituted_sku,
                                "unit_price": unit_price,
                                "line_total": line_total,
                            }
                        )
                        + "\n"
                    )
                    ol_seq += 1

                order_total = round(order_total, 2)
                case_fill_rate = round(tot_shipped_cases / tot_ordered_cases, 4) if tot_ordered_cases > 0 else 0.0
                order_status = "FILLED" if tot_shipped_cases == tot_ordered_cases else "SHORT_SHIPPED"

                ord_buf.append(
                    json.dumps(
                        {
                            "order_id": order_id,
                            "customer_id": cid,
                            "dc_id": dc_id,
                            "order_date": date_str,
                            "scheduled_delivery_date": sched_deliv_date.isoformat(),
                            "order_status": order_status,
                            "ordered_cases": tot_ordered_cases,
                            "shipped_cases": tot_shipped_cases,
                            "case_fill_rate": case_fill_rate,
                            "order_total": order_total,
                        }
                    )
                    + "\n"
                )

                # Build corresponding shipment record
                route_id = cust_route[cid]
                if has_frozen:
                    load_temp_zone = "frozen"
                elif has_refrigerated:
                    load_temp_zone = "refrigerated"
                else:
                    load_temp_zone = "ambient"

                sched_hour = rng.randint(5, 11)
                sched_min = rng.choice([0, 15, 30, 45])
                sched_dt = dt.datetime.combine(
                    sched_deliv_date, dt.time(sched_hour, sched_min), tzinfo=dt.timezone.utc
                )

                on_time_prob = 0.87 if dc_id == UNDERPERFORMING_DC else 0.94
                if rng.random() < on_time_prob:
                    delta_mins = rng.randint(-25, 25)
                    on_time = True
                else:
                    delta_mins = rng.randint(35, 195)
                    on_time = False
                actual_dt = sched_dt + dt.timedelta(minutes=delta_mins)

                # PATTERN 4: Cluster of cold-chain temperature excursions on route RTE-SW-404
                if load_temp_zone in ("refrigerated", "frozen"):
                    if route_id == EXCURSION_ROUTE:
                        excursion_prob = 0.42 if month in (5, 6, 7, 8, 9) else 0.24
                    else:
                        excursion_prob = 0.008
                    temp_excursion = rng.random() < excursion_prob
                    if load_temp_zone == "refrigerated":
                        peak_temp_f = round(rng.uniform(44.5, 53.0) if temp_excursion else rng.uniform(34.0, 39.5), 1)
                    else:
                        peak_temp_f = round(rng.uniform(14.0, 26.5) if temp_excursion else rng.uniform(-10.0, 2.0), 1)
                else:
                    temp_excursion = None
                    peak_temp_f = None

                shp_buf.append(
                    json.dumps(
                        {
                            "shipment_id": f"SHP-{shp_seq:07d}",
                            "order_id": order_id,
                            "dc_id": dc_id,
                            "customer_id": cid,
                            "route_id": route_id,
                            "load_temp_zone": load_temp_zone,
                            "scheduled_delivery": sched_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "actual_delivery": actual_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "on_time": on_time,
                            "temperature_excursion": temp_excursion,
                            "peak_temp_f": peak_temp_f,
                        }
                    )
                    + "\n"
                )
                shp_seq += 1

            if len(ol_buf) >= 25000:
                f_ord.writelines(ord_buf)
                f_ol.writelines(ol_buf)
                f_shp.writelines(shp_buf)
                ord_buf.clear()
                ol_buf.clear()
                shp_buf.clear()

        if ord_buf:
            f_ord.writelines(ord_buf)
            f_ol.writelines(ol_buf)
            f_shp.writelines(shp_buf)

    return {
        "orders": order_seq - 1,
        "order_lines": ol_seq - 1,
        "shipments": shp_seq - 1,
    }


def generate_inventory_snapshots(
    rng: random.Random,
    dcs: list[dict[str, Any]],
    products: list[dict[str, Any]],
    snapshots_path: Path,
) -> int:
    """Generate daily DC x SKU inventory snapshots across the 18-month period.

    Tracks all 600 SKUs across all 7 DCs for 548 days = 2,301,600 rows (~281 MB).
    """
    total_days = (END_DATE - START_DATE).days + 1
    date_strings = [
        (START_DATE + dt.timedelta(days=d)).isoformat() for d in range(total_days)
    ]
    date_months = [
        (START_DATE + dt.timedelta(days=d)).month for d in range(total_days)
    ]
    is_last_q = [
        (START_DATE + dt.timedelta(days=d)) >= LAST_QUARTER_START
        for d in range(total_days)
    ]

    row_count = 0
    with snapshots_path.open("w", encoding="utf-8") as f_inv:
        buf: list[str] = []
        for dc in dcs:
            dc_id = dc["dc_id"]
            is_under_dc = dc_id == UNDERPERFORMING_DC

            for prod in products:
                sku = prod["sku"]
                cat = prod["category"]
                is_degrading_sup = prod["primary_supplier_id"] in DEGRADING_SUPPLIERS

                base_daily_demand = rng.uniform(6.0, 18.0)
                safety_stock = max(12, int(round(base_daily_demand * (3.2 if is_under_dc else 5.5))))
                on_hand = int(round(base_daily_demand * (6.5 if is_under_dc else 12.0)))
                replenish_qty = int(round(base_daily_demand * 10.0))

                for d_idx in range(total_days):
                    month = date_months[d_idx]
                    d_str = date_strings[d_idx]
                    demand_mult = 1.0
                    if cat == "produce" and month in (6, 7, 8):
                        demand_mult = 1.65
                    elif cat == "protein" and month in (11, 12):
                        demand_mult = 1.75

                    daily_draw = int(round(base_daily_demand * demand_mult * rng.uniform(0.75, 1.25)))
                    on_hand = max(0, on_hand - daily_draw)

                    # Trigger replenishment based on safety stock & supplier/DC health
                    reorder_threshold = int(safety_stock * (0.75 if is_under_dc else 1.25))
                    if is_degrading_sup and is_last_q[d_idx]:
                        reorder_threshold = int(safety_stock * 0.45)

                    if on_hand <= reorder_threshold:
                        # Occasional delayed replenishment causes authentic stockout days at DC-SE-01 or degrading suppliers
                        skip_prob = 0.35 if (is_under_dc or (is_degrading_sup and is_last_q[d_idx])) else 0.04
                        if rng.random() >= skip_prob:
                            on_hand += replenish_qty

                    eff_daily_demand = base_daily_demand * demand_mult
                    days_of_supply = round(on_hand / eff_daily_demand, 2)

                    buf.append(
                        f'{{"snapshot_date":"{d_str}","dc_id":"{dc_id}","sku":"{sku}",'
                        f'"on_hand_cases":{on_hand},"safety_stock":{safety_stock},'
                        f'"days_of_supply":{days_of_supply}}}\n'
                    )
                    row_count += 1

                    if len(buf) >= 50000:
                        f_inv.writelines(buf)
                        buf.clear()

        if buf:
            f_inv.writelines(buf)
            buf.clear()

    return row_count


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> int:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return len(rows)


def main() -> None:
    t0 = time.perf_counter()
    rng = random.Random(SEED)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[sfs.generate] Generating Stark Food Services synthetic dataset (seed={SEED})...")
    print(f"[sfs.generate] Date range: {START_DATE.isoformat()} to {END_DATE.isoformat()} (18 months)")

    dcs = build_distribution_centers()
    suppliers = build_suppliers(rng)
    products = build_products(rng, suppliers)
    customers, contacts = build_customers_and_contacts(rng, dcs)
    pos, po_lines, ap_records = build_po_and_ap(rng, dcs, suppliers, products)

    counts: dict[str, int] = {}
    counts["distribution_centers"] = write_jsonl(DATA_DIR / "distribution_centers.jsonl", dcs)
    counts["suppliers"] = write_jsonl(DATA_DIR / "suppliers.jsonl", suppliers)
    counts["products"] = write_jsonl(DATA_DIR / "products.jsonl", products)
    counts["customers"] = write_jsonl(DATA_DIR / "customers.jsonl", customers)
    counts["customer_contacts"] = write_jsonl(DATA_DIR / "customer_contacts.jsonl", contacts)
    counts["purchase_orders"] = write_jsonl(DATA_DIR / "purchase_orders.jsonl", pos)
    counts["po_lines"] = write_jsonl(DATA_DIR / "po_lines.jsonl", po_lines)
    counts["accounts_payable"] = write_jsonl(DATA_DIR / "accounts_payable.jsonl", ap_records)

    ord_counts = generate_orders_lines_shipments(
        rng=rng,
        dcs=dcs,
        customers=customers,
        products=products,
        orders_path=DATA_DIR / "orders.jsonl",
        order_lines_path=DATA_DIR / "order_lines.jsonl",
        shipments_path=DATA_DIR / "shipments.jsonl",
    )
    counts.update(ord_counts)

    counts["inventory_snapshots"] = generate_inventory_snapshots(
        rng=rng,
        dcs=dcs,
        products=products,
        snapshots_path=DATA_DIR / "inventory_snapshots.jsonl",
    )

    elapsed = time.perf_counter() - t0
    total_bytes = sum(p.stat().st_size for p in DATA_DIR.glob("*.jsonl"))
    total_mb = total_bytes / (1024 * 1024)

    print("\n[sfs.generate] Generation complete!")
    print(f"  Elapsed time : {elapsed:.2f}s")
    print(f"  Total size   : {total_mb:.2f} MB across {len(counts)} tables in {DATA_DIR}")
    for table, count in counts.items():
        size_mb = (DATA_DIR / f"{table}.jsonl").stat().st_size / (1024 * 1024)
        print(f"  - {table:<22}: {count:>10,} rows ({size_mb:>6.2f} MB)")


if __name__ == "__main__":
    main()
