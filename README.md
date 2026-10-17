# Stark Food Services (SFS)

**Stark Food Services (SFS)** is a fictional US broadline foodservice distributor operating 7 regional distribution centers across the United States. This repository generates a deterministic, referentially intact synthetic supply-chain dataset (18 months of daily history, ~2.69M total rows, ~373 MB of newline-delimited JSON), defines the BigQuery schema DDL (`sql/schema.sql`), and provides automated data-quality and pattern verification (`src/sfs/validate.py`).

---

## Repository Structure

```text
stark-food-services/
├── .gitignore               # Excludes .venv/, .env, *.json keys, and generated data/
├── Makefile                 # Build, data generation, and validation targets
├── README.md                # Full schema dictionary & intentional pattern documentation
├── pyproject.toml           # Python 3.11+ package configuration (src/sfs layout)
├── tools.yaml               # MCP Toolbox for Databases configuration (7 read + 2 action tools)
├── scripts/
│   └── load_bq.sh           # Idempotent BigQuery loader (--replace) for data/*.jsonl
├── sql/
│   ├── schema.sql           # Project-agnostic BigQuery DDL for all 12 sfs_demo tables
│   └── validate.sql         # BigQuery integrity & analytical pattern discovery queries
└── src/
    └── sfs/
        ├── __init__.py      # Package metadata
        ├── generate.py      # Deterministic (seed=42) synthetic data generator
        └── validate.py      # Referential-integrity & analytical pattern validator
```

---

## Quick Start

Requires **Python 3.11+** (zero external third-party packages required; uses the Python standard library).

```bash
# 1. Create virtual environment
make venv
# (or: python3 -m venv .venv)

# 2. Generate 18 months of synthetic data into data/*.jsonl (~2.3s)
make generate
# (or: PYTHONPATH=src .venv/bin/python -m sfs.generate)

# 3. Validate row counts, primary/foreign keys, and analytical patterns (~2.6s)
make validate
# (or: PYTHONPATH=src .venv/bin/python -m sfs.validate)

# 4. Create BigQuery tables and load all data/*.jsonl into dataset sfs_demo (US)
bq --location=US query --use_legacy_sql=false < sql/schema.sql
make load

# 5. Run BigQuery SQL validation & pattern discovery queries
bq --location=US query --use_legacy_sql=false < sql/validate.sql
```

---

## Dataset Scale & Summary Statistics

- **Random Seed**: `42` (100% deterministic output)
- **Historical Window**: `2025-04-01` through `2026-09-30` (18 months / 548 calendar days)
- **Output Format**: Newline-delimited JSON (`data/*.jsonl`, gitignored)

| Table | File | Row Count | Size (MB) | Grain |
|---|---|---:|---:|---|
| `sfs_demo.distribution_centers` | `data/distribution_centers.jsonl` | 7 | 0.00 | 1 row per regional SFS distribution center |
| `sfs_demo.suppliers` | `data/suppliers.jsonl` | 42 | 0.01 | 1 row per foodservice vendor/grower/packer |
| `sfs_demo.products` | `data/products.jsonl` | 600 | 0.19 | 1 row per catalog SKU |
| `sfs_demo.customers` | `data/customers.jsonl` | 400 | 0.09 | 1 row per foodservice operator account |
| `sfs_demo.customer_contacts` | `data/customer_contacts.jsonl` | 743 | 0.16 | 1 row per operator contact (**PII-bearing**) |
| `sfs_demo.purchase_orders` | `data/purchase_orders.jsonl` | 8,848 | 2.86 | 1 row per inbound supplier replenishment PO |
| `sfs_demo.po_lines` | `data/po_lines.jsonl` | 39,797 | 6.67 | 1 row per replenishment PO line item |
| `sfs_demo.accounts_payable` | `data/accounts_payable.jsonl` | 8,848 | 3.56 | 1 row per supplier remittance (**Sensitive banking/tax**) |
| `sfs_demo.orders` | `data/orders.jsonl` | 41,175 | 10.36 | 1 row per outbound customer sales order |
| `sfs_demo.order_lines` | `data/order_lines.jsonl` | 250,272 | 55.36 | 1 row per customer order line item |
| `sfs_demo.shipments` | `data/shipments.jsonl` | 41,175 | 12.63 | 1 row per outbound route shipment |
| `sfs_demo.inventory_snapshots` | `data/inventory_snapshots.jsonl` | 2,301,600 | 281.29 | Daily `DC x SKU` end-of-day inventory snapshot |
| **Total** | | **2,693,507** | **373.18** | |

---

## BigQuery Partitioning & Clustering Strategy

All high-volume fact and line-item tables in [`sql/schema.sql`](sql/schema.sql) are partitioned by their primary event date (`DAY` granularity) and clustered on high-cardinality filter/join keys (`dc_id`, `sku`, `customer_id`, `supplier_id`, `route_id`) to minimize bytes scanned by analytical queries and AI agents:

| Table | Time Partitioning (`DAY`) | Clustered Columns | Rationale |
|---|---|---|---|
| `sfs_demo.inventory_snapshots` | `snapshot_date` | `dc_id, sku` | Largest table (`2.30M` rows). Date-range queries over DC inventory positions and SKU stockout rates prune partitions by `snapshot_date` and co-locate blocks by `dc_id` and `sku`. |
| `sfs_demo.order_lines` | `order_date` | `dc_id, sku, customer_id` | Denormalized `order_date`, `dc_id`, and `customer_id` onto line items (`251k` rows) so seasonal category demand, DC case fill rates, and customer SKU history scan only relevant dates and blocks without expensive header joins. |
| `sfs_demo.po_lines` | `order_date` | `dc_id, sku` | Denormalized `order_date` and `dc_id` onto replenishment lines (`39.9k` rows) for fast inbound SKU receipt and short-ship analysis by date window, facility, and item. |
| `sfs_demo.shipments` | `DATE(scheduled_delivery)` | `dc_id, customer_id, route_id` | Partitioned by scheduled delivery date (extracted from `TIMESTAMP`) and clustered by `dc_id`, `customer_id`, and `route_id` to accelerate cold-chain temperature excursion and route on-time investigations. |
| `sfs_demo.orders` | `order_date` | `dc_id, customer_id` | Optimizes order-level fill rate rollups by DC and customer churn cohort windowing (`final 8 weeks` vs `prior 70 weeks`). |
| `sfs_demo.purchase_orders` | `order_date` | `dc_id, supplier_id` | Optimizes supplier lead-time degradation comparisons across quarters (`Q1–Q5` vs `Q6`) and DC receiving analytics. |
| `sfs_demo.accounts_payable` | `payment_date` | `supplier_id` | Optimizes treasury disbursement audits and supplier remittance lookups by date and payee. |
| `sfs_demo.products` | *(None — 600 rows)* | `sku, category, temp_zone` | Dimension table clustered for category and temperature-zone filtering. |
| `sfs_demo.customers` | *(None — 400 rows)* | `assigned_dc_id, customer_id, segment` | Dimension table clustered for regional DC and operator segment lookups. |
| `sfs_demo.customer_contacts` | *(None — 743 rows)* | `customer_id` | Co-locates contact records by parent customer account. |

---

## Schema Reference (Every Table & Column)

All DDL definitions reside in [`sql/schema.sql`](sql/schema.sql) under the `sfs_demo` dataset schema (location `US`).

### 1. `sfs_demo.suppliers`
Foodservice product manufacturers, growers, and processors supplying SFS distribution centers.

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `supplier_id` | `STRING` | `NOT NULL` | Primary key (`SUP-001` .. `SUP-042`) |
| `name` | `STRING` | `NOT NULL` | Legal or trade name of the supplier |
| `region` | `STRING` | `NOT NULL` | US geographic region of primary operations |
| `primary_category` | `STRING` | `NOT NULL` | Primary product category supplied (`produce`, `protein`, `dairy`, `dry`, `frozen`, `paper`, `chemical`) |
| `contracted_lead_time_days` | `INT64` | `NOT NULL` | Contracted replenishment lead time in calendar days (2–9 days) |
| `reliability_profile` | `STRING` | `NOT NULL` | Reliability tier (`tier_1_reliable`, `standard`, `variable`, `degrading_last_quarter`) |
| `baseline_on_time_rate` | `FLOAT64` | `NOT NULL` | Historical baseline on-time delivery probability (`0.84`–`0.98`) |

### 2. `sfs_demo.distribution_centers`
Regional broadline distribution centers operated by Stark Food Services.

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `dc_id` | `STRING` | `NOT NULL` | Primary key (`DC-NE-01`, `DC-MA-01`, `DC-SE-01`, `DC-MW-01`, `DC-SW-01`, `DC-WE-01`, `DC-NW-01`) |
| `name` | `STRING` | `NOT NULL` | Distribution center facility name |
| `city` | `STRING` | `NOT NULL` | Facility city (`Newark`, `Baltimore`, `Atlanta`, `Chicago`, `Dallas`, `Ontario`, `Seattle`) |
| `state` | `STRING` | `NOT NULL` | Two-letter US state code (`NJ`, `MD`, `GA`, `IL`, `TX`, `CA`, `WA`) |
| `region` | `STRING` | `NOT NULL` | US geographic region (`Northeast`, `Mid-Atlantic`, `Southeast`, `Midwest`, `Southwest`, `West`, `Pacific Northwest`) |
| `capacity_cases` | `INT64` | `NOT NULL` | Total storage capacity in cases across all temperature zones |
| `cold_storage_capacity_cases` | `INT64` | `NOT NULL` | Combined refrigerated and frozen storage capacity in cases |

### 3. `sfs_demo.products`
Master catalog of 600 foodservice SKUs across 7 categories and 3 temperature zones.

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `sku` | `STRING` | `NOT NULL` | Primary key (`SKU-10001` .. `SKU-10600`) |
| `description` | `STRING` | `NOT NULL` | Commercial product description including brand, grade, and pack size |
| `category` | `STRING` | `NOT NULL` | Product category: `produce` (95), `protein` (105), `dairy` (75), `dry` (130), `frozen` (95), `paper` (60), `chemical` (40) |
| `brand` | `STRING` | `NOT NULL` | National or SFS private-label brand name |
| `pack_size` | `STRING` | `NOT NULL` | Standard foodservice case pack configuration (e.g., `4/5 lb`, `6/#10 can`, `1/500 ct`) |
| `case_cost` | `NUMERIC(10,2)` | `NOT NULL` | Distributor wholesale acquisition cost per case in USD |
| `list_price` | `NUMERIC(10,2)` | `NOT NULL` | Standard operator list price per case in USD |
| `temp_zone` | `STRING` | `NOT NULL` | Required storage/transport temperature zone (`ambient`, `refrigerated`, `frozen`) |
| `shelf_life_days` | `INT64` | `NOT NULL` | Expected shelf life in calendar days from receipt |
| `primary_supplier_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.suppliers.supplier_id` |
| `substitute_sku` | `STRING` | `NULL` | Foreign key to `sfs_demo.products.sku` within the same category and temperature zone |

### 4. `sfs_demo.customers`
Foodservice operator customer accounts (400 operators across 4 segments).

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `customer_id` | `STRING` | `NOT NULL` | Primary key (`CUST-0001` .. `CUST-0400`) |
| `operator_name` | `STRING` | `NOT NULL` | Foodservice operator business or institution name |
| `segment` | `STRING` | `NOT NULL` | Market segment: `restaurant`, `healthcare`, `education`, `hospitality` |
| `region` | `STRING` | `NOT NULL` | Customer geographic region |
| `credit_terms` | `STRING` | `NOT NULL` | Contracted payment terms (`Net 15`, `Net 30`, `Net 45`, `COD`) |
| `assigned_dc_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.distribution_centers.dc_id` |
| `account_open_date` | `DATE` | `NOT NULL` | Date the operator account was established (`YYYY-MM-DD`) |

### 5. `sfs_demo.customer_contacts` *(Intentionally PII-Bearing)*
Customer contact directory containing personal identifiers for data-governance and column-masking demonstrations.

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `contact_id` | `STRING` | `NOT NULL` | Primary key (`CONT-00001` .. `CONT-00743`) |
| `customer_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.customers.customer_id` |
| `name` | `STRING` | `NOT NULL` | **PII**: Full name of the customer contact |
| `email` | `STRING` | `NOT NULL` | **PII**: Direct email address of the contact |
| `phone` | `STRING` | `NOT NULL` | **PII**: Direct US telephone number (`+1-AAA-555-XXXX`) |
| `role` | `STRING` | `NOT NULL` | Job title (`Executive Chef`, `Director of Purchasing`, `Kitchen Manager`, `Food & Beverage Director`, `Accounts Payable Lead`, `General Manager`) |
| `is_primary` | `BOOL` | `NOT NULL` | `true` for the primary contact on the customer account |

### 6. `sfs_demo.purchase_orders`
Inbound replenishment purchase order headers from suppliers to SFS distribution centers.

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `po_id` | `STRING` | `NOT NULL` | Primary key (`PO-000001` .. `PO-008848`) |
| `supplier_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.suppliers.supplier_id` |
| `dc_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.distribution_centers.dc_id` |
| `order_date` | `DATE` | `NOT NULL` | Date PO was issued to supplier |
| `expected_delivery_date` | `DATE` | `NOT NULL` | Scheduled delivery date (`order_date + contracted_lead_time_days`) |
| `actual_delivery_date` | `DATE` | `NOT NULL` | Actual dock receipt date (`order_date + actual_lead_time_days`) |
| `contracted_lead_time_days` | `INT64` | `NOT NULL` | Contracted lead time in calendar days |
| `actual_lead_time_days` | `INT64` | `NOT NULL` | Actual elapsed lead time in calendar days |
| `status` | `STRING` | `NOT NULL` | Receipt status (`RECEIVED`, `LATE_RECEIVED`, `PARTIAL`) |
| `total_ordered_cases` | `INT64` | `NOT NULL` | Total cases ordered across all lines on the PO |
| `total_received_cases` | `INT64` | `NOT NULL` | Total cases received across all lines on the PO |
| `total_cost` | `NUMERIC(12,2)` | `NOT NULL` | Total landed cost of received cases in USD |

### 7. `sfs_demo.po_lines`
Line-item detail for inbound supplier replenishment purchase orders.

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `po_line_id` | `STRING` | `NOT NULL` | Primary key (`POL-0000001` .. `POL-0039936`) |
| `po_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.purchase_orders.po_id` |
| `order_date` | `DATE` | `NOT NULL` | Date parent PO was issued (partition key) |
| `dc_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.distribution_centers.dc_id` (cluster key) |
| `line_number` | `INT64` | `NOT NULL` | Sequential line number within the PO |
| `sku` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.products.sku` |
| `ordered_cases` | `INT64` | `NOT NULL` | Cases ordered on this PO line |
| `received_cases` | `INT64` | `NOT NULL` | Cases actually received at the DC dock |
| `case_cost` | `NUMERIC(10,2)` | `NOT NULL` | Unit wholesale cost per case in USD |
| `line_cost` | `NUMERIC(12,2)` | `NOT NULL` | Extended cost (`received_cases * case_cost`) in USD |

### 8. `sfs_demo.accounts_payable` *(Intentionally Sensitive Financial Records)*
Supplier remittance and banking records designed for column-level security, policy tag, and DLP governance demos.

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `remittance_id` | `STRING` | `NOT NULL` | Primary key (`AP-000001` .. `AP-008848`) |
| `po_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.purchase_orders.po_id` |
| `supplier_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.suppliers.supplier_id` |
| `invoice_number` | `STRING` | `NOT NULL` | Supplier invoice reference number |
| `invoice_date` | `DATE` | `NOT NULL` | Invoice date (matches PO actual receipt date) |
| `payment_date` | `DATE` | `NOT NULL` | Date electronic remittance was disbursed |
| `payment_amount` | `NUMERIC(12,2)` | `NOT NULL` | Total USD amount remitted to supplier |
| `payment_method` | `STRING` | `NOT NULL` | Disbursement method (`ACH`, `EFT`, `WIRE`) |
| `bank_name` | `STRING` | `NOT NULL` | **SENSITIVE**: Receiving financial institution name |
| `aba_routing_number` | `STRING` | `NOT NULL` | **SENSITIVE**: 9-digit US ABA bank routing number |
| `bank_account_number` | `STRING` | `NOT NULL` | **SENSITIVE**: Unmasked 10-digit receiving bank account number |
| `supplier_tax_id` | `STRING` | `NOT NULL` | **SENSITIVE**: Supplier federal EIN (`XX-XXXXXXX`) |
| `remittance_email` | `STRING` | `NOT NULL` | **SENSITIVE**: Supplier treasury/remittance advice email |

### 9. `sfs_demo.inventory_snapshots`
Daily end-of-day inventory position across all 7 DCs and 600 SKUs over 548 days (`2,301,600` rows).

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `snapshot_date` | `DATE` | `NOT NULL` | Calendar date of end-of-day snapshot (`2025-04-01` .. `2026-09-30`) |
| `dc_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.distribution_centers.dc_id` |
| `sku` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.products.sku` |
| `on_hand_cases` | `INT64` | `NOT NULL` | Physical cases available on hand at end of day |
| `safety_stock` | `INT64` | `NOT NULL` | Target minimum safety stock buffer in cases |
| `days_of_supply` | `FLOAT64` | `NOT NULL` | Estimated days of supply based on trailing daily demand rate |

### 10. `sfs_demo.orders`
Customer outbound sales order headers.

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `order_id` | `STRING` | `NOT NULL` | Primary key (`ORD-0000001` .. `ORD-0041175`) |
| `customer_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.customers.customer_id` |
| `dc_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.distribution_centers.dc_id` |
| `order_date` | `DATE` | `NOT NULL` | Date customer placed the order |
| `scheduled_delivery_date` | `DATE` | `NOT NULL` | Scheduled customer delivery date |
| `order_status` | `STRING` | `NOT NULL` | Order fulfillment status (`FILLED`, `SHORT_SHIPPED`) |
| `ordered_cases` | `INT64` | `NOT NULL` | Total cases ordered across all lines |
| `shipped_cases` | `INT64` | `NOT NULL` | Total cases shipped (including substitutions) |
| `case_fill_rate` | `FLOAT64` | `NOT NULL` | Ratio `shipped_cases / ordered_cases` (`0.0`–`1.0`) |
| `order_total` | `NUMERIC(12,2)` | `NOT NULL` | Total invoiced order amount in USD for shipped cases |

### 11. `sfs_demo.order_lines`
Customer order line items (`250,272` rows) tracking ordered vs. shipped cases, out-of-stocks, and substitutions.

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `order_line_id` | `STRING` | `NOT NULL` | Primary key (`OL-0000001` .. `OL-0251052`) |
| `order_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.orders.order_id` |
| `order_date` | `DATE` | `NOT NULL` | Date customer placed the parent order (partition key) |
| `dc_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.distribution_centers.dc_id` (cluster key) |
| `customer_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.customers.customer_id` (cluster key) |
| `line_number` | `INT64` | `NOT NULL` | Sequential line number within the order |
| `sku` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.products.sku` (originally ordered SKU) |
| `ordered_cases` | `INT64` | `NOT NULL` | Number of cases requested by customer |
| `shipped_cases` | `INT64` | `NOT NULL` | Number of cases actually shipped (`0` when `OUT_OF_STOCK`) |
| `fill_status` | `STRING` | `NOT NULL` | Line outcome: `FILLED`, `PARTIAL`, `OUT_OF_STOCK`, `SUBSTITUTED` |
| `substituted_sku` | `STRING` | `NULL` | Foreign key to `sfs_demo.products.sku` when `fill_status = 'SUBSTITUTED'` (`NULL` otherwise) |
| `unit_price` | `NUMERIC(10,2)` | `NOT NULL` | Billed price per case in USD |
| `line_total` | `NUMERIC(12,2)` | `NOT NULL` | Extended line total in USD (`shipped_cases * unit_price`) |

### 12. `sfs_demo.shipments`
Outbound delivery shipments with route assignment, delivery timestamps, on-time flag, and cold-chain excursion telemetry.

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `shipment_id` | `STRING` | `NOT NULL` | Primary key (`SHP-0000001` .. `SHP-0041175`) |
| `order_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.orders.order_id` |
| `dc_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.distribution_centers.dc_id` |
| `customer_id` | `STRING` | `NOT NULL` | Foreign key to `sfs_demo.customers.customer_id` |
| `route_id` | `STRING` | `NOT NULL` | Assigned delivery route identifier (42 routes across 7 DCs, e.g., `RTE-SW-404`) |
| `load_temp_zone` | `STRING` | `NOT NULL` | Most stringent temperature zone required by the shipment (`ambient`, `refrigerated`, `frozen`) |
| `scheduled_delivery` | `TIMESTAMP` | `NOT NULL` | Scheduled delivery appointment timestamp (ISO-8601 UTC) |
| `actual_delivery` | `TIMESTAMP` | `NOT NULL` | Actual dock arrival timestamp (ISO-8601 UTC) |
| `on_time` | `BOOL` | `NOT NULL` | `true` if `actual_delivery` is within 30 minutes of `scheduled_delivery` |
| `temperature_excursion` | `BOOL` | `NULL` | For `refrigerated`/`frozen` loads, `true` if compartment temp exceeded safe threshold (`NULL` for `ambient`) |
| `peak_temp_f` | `FLOAT64` | `NULL` | Peak compartment temperature (°F) during transit for cold-chain loads (`NULL` for `ambient`) |


### 13. `sfs_demo.replenishment_drafts` *(Append-Only Agent Action Table)*
Append-only staging table written by the `create_replenishment_draft` MCP tool.

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `draft_id` | `STRING` | `NOT NULL` | Primary key (`GENERATE_UUID()`) |
| `created_at` | `TIMESTAMP` | `NOT NULL` | UTC timestamp when the replenishment draft was created (`PARTITION BY DATE(created_at)`) |
| `dc_id` | `STRING` | `NOT NULL` | Target distribution center ID (`CLUSTER BY dc_id, sku`) |
| `sku` | `STRING` | `NOT NULL` | Product SKU requested for replenishment |
| `cases_requested` | `INT64` | `NOT NULL` | Number of cases requested |
| `rationale` | `STRING` | `NOT NULL` | Analytical rationale or agent justification for the draft |
| `created_by` | `STRING` | `NOT NULL` | Identity of the MCP server or workflow (`sfs-mcp-toolbox`) |

### 14. `sfs_demo.customer_flags` *(Append-Only Agent Action Table)*
Append-only staging table written by the `flag_customer_for_outreach` MCP tool.

| Column | BigQuery Type | Nullable | Description |
|---|---|---|---|
| `flag_id` | `STRING` | `NOT NULL` | Primary key (`GENERATE_UUID()`) |
| `created_at` | `TIMESTAMP` | `NOT NULL` | UTC timestamp when the customer flag was recorded (`PARTITION BY DATE(created_at)`) |
| `customer_id` | `STRING` | `NOT NULL` | Flagged customer account ID (`CLUSTER BY customer_id, flag_type`) |
| `flag_type` | `STRING` | `NOT NULL` | Outreach classification (`CHURN_RISK`, `SERVICE_RECOVERY`, `COLD_CHAIN_REVIEW`) |
| `note` | `STRING` | `NOT NULL` | Actionable context note for the account management team |
| `created_by` | `STRING` | `NOT NULL` | Identity of the MCP server or workflow (`sfs-mcp-toolbox`) |

---

## Least-privilege tool surface

The MCP server configured in [`tools.yaml`](tools.yaml) (powered by **MCP Toolbox for Databases**) exposes a deliberately narrow, parameterized tool surface rather than unrestricted `execute_sql` or raw schema access:

1. **Complete Exclusion of Sensitive Financial Records (`sfs_demo.accounts_payable`)**:
   - Even though `sfs_demo.accounts_payable` resides in the same BigQuery dataset (`sfs_demo`) and contains unmasked ABA routing numbers, bank account numbers, federal EINs (`supplier_tax_id`), and treasury remittance emails, **zero tools in `tools.yaml` reference `accounts_payable`**. An AI agent connected via MCP cannot query, infer, or exfiltrate supplier banking or tax records.
2. **Column-Level PII Exclusion on `sfs_demo.customer_contacts`**:
   - `sfs_demo.customer_contacts` contains personal names (`name`), direct email addresses (`email`), and phone numbers (`phone`). The MCP tools (`churn_risk_customers` and `customer_order_summary`) only project `customer_id` and aggregated job `role` (e.g., `Executive Chef`, `Director of Purchasing`) so the agent knows *which role* to engage without ever receiving PII.
3. **Parameterized, Bounded Read Tools with Cost Guards**:
   - All 7 read tools (`supplier_lead_time_performance`, `dc_fill_rate`, `stockout_risk_skus`, `cold_chain_excursions`, `churn_risk_customers`, `customer_order_summary`, `product_search`) use strongly typed BigQuery query parameters (`@param` — zero string interpolation), explicit `LIMIT` clauses (`<= 25` rows), `maxQueryResultRows: 50`, and `maximumBytesBilled: 250000000` (250 MB) on the `sfs-bq` source.
4. **Append-Only Action Tools**:
   - Write operations (`create_replenishment_draft` and `flag_customer_for_outreach`) are strictly confined to `INSERT` statements into the two dedicated append-only staging tables (`sfs_demo.replenishment_drafts` and `sfs_demo.customer_flags`). No tool can `UPDATE`, `DELETE`, or `DROP` operational supply-chain records.

---

## Intentional Analytical Patterns (Discoverable by Analyst Agents)

The generator bakes in six realistic, non-random supply-chain anomalies designed for discovery by Gemini Enterprise and SQL analysts:

### 1. Two Suppliers with Severe Lead-Time Degradation in the Final Quarter
- **Entities**:
  - `SUP-002` (**SunCoast Fresh Growers** — Southeast `produce` supplier, `contracted_lead_time_days = 3`)
  - `SUP-008` (**Heartland Prime Meats** — Midwest `protein` supplier, `contracted_lead_time_days = 4`)
- **Behavior**: During the first 15 months (`2025-04-01` to `2026-06-30`), both suppliers deliver reliably near their contracted lead times (`3.20d` and `4.13d` average). Starting `2026-07-01` (the final quarter), their actual lead times deteriorate progressively each month (`12.09d` average / **+278.0%** for `SUP-002`; `12.68d` average / **+206.9%** for `SUP-008`), while the other 40 suppliers remain steady (`5.70d` vs `5.67d`).

### 2. Seasonal Category Demand Swings
- **Produce Summer Spike**: In June, July, and August (`month IN (6, 7, 8)`), `produce` order line selection frequency and ordered cases per line surge, lifting monthly ordered produce volume to **72,714 cases/month** vs **28,536 cases/month** in non-summer months (**2.55x lift**).
- **Protein Holiday Spike**: In November and December (`month IN (11, 12)`), holiday dining and banquet demand lifts `protein` volume to **75,674 cases/month** vs **27,670 cases/month** in non-holiday months (**2.73x lift**).

### 3. Materially Worse Case Fill Rate at One Distribution Center
- **Entity**: `DC-SE-01` (**SFS Southeast Hub DC — Atlanta, GA**)
- **Behavior**: While the other 6 DCs maintain industry-standard case fill rates between **97.60% and 97.90%** (and daily snapshot stockout rates of `0.01%`), `DC-SE-01` suffers chronic safety-stock compression and higher out-of-stock/short-ship rates, resulting in an overall case fill rate of **85.54%** (~12.2 percentage points below peer DCs) and a daily inventory stockout rate of **0.65%**.

### 4. Cold-Chain Temperature Excursion Cluster on One Route
- **Entity**: Route `RTE-SW-404` (operating out of `DC-SW-01` Dallas, TX)
- **Behavior**: Across the other 41 delivery routes, cold-chain (`refrigerated` and `frozen`) shipments experience a baseline temperature excursion rate of **0.86%** (`343 / 39,978` loads). On `RTE-SW-404`, a failing multi-temp reefer trailer causes a **30.87% excursion rate** (`276 / 894` cold-chain loads, peaking above 40% during May–September).

### 5. ~15 Customers with Sharp Order Volume Drop in the Final 8 Weeks (Churn Risk)
- **Entities**: 15 customer accounts (`CUST-0015`, `CUST-0042`, `CUST-0068`, `CUST-0095`, `CUST-0122`, `CUST-0149`, `CUST-0176`, `CUST-0203`, `CUST-0230`, `CUST-0257`, `CUST-0284`, `CUST-0311`, `CUST-0338`, `CUST-0365`, `CUST-0392`)
- **Behavior**: Across the first 70 weeks (`2025-04-01` to `2026-08-05`), these 15 accounts are high-cadence buyers averaging **249.9 ordered cases/week**. In the final 8 weeks (`2026-08-06` to `2026-09-30`), their order frequency and basket size plummet to **5.1 cases/week** (**-97.9%**), whereas the other 385 accounts remain stable (**88.9** -> **91.4 cases/week**, **+2.8%**).

### 6. Realistic Out-of-Stock and Substitution Rates by Category
- **Behavior**: Line fulfillment outcomes reflect physical product characteristics across all `250,272` order lines:
  - `produce` (short shelf life, weather-sensitive): `4.16%` OOS, `5.53%` partial, `5.33%` substituted (`84.99%` filled as ordered)
  - `protein`: `2.93%` OOS, `4.05%` partial, `3.48%` substituted (`89.53%` filled)
  - `dairy`: `2.18%` OOS, `3.00%` partial, `4.41%` substituted (`90.41%` filled)
  - `frozen`: `1.43%` OOS, `2.29%` partial, `2.72%` substituted (`93.56%` filled)
  - `dry`: `1.08%` OOS, `1.60%` partial, `2.04%` substituted (`95.28%` filled)
  - `paper`: `0.73%` OOS, `1.31%` partial, `3.02%` substituted (`94.93%` filled)
  - `chemical` (proprietary dispenser hardware): `0.62%` OOS, `1.08%` partial, **`0.22%` substituted** (`98.08%` filled)
