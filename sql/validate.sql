-- =============================================================================
-- Stark Food Services (SFS) — BigQuery Validation & Pattern Discovery Queries
-- Dataset: sfs_demo (project-agnostic; never hardcode project IDs)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Row Counts, Null-Key Checks, and Duplicate Key Checks per Table
-- -----------------------------------------------------------------------------
SELECT * FROM (
  SELECT '1_distribution_centers' AS table_name, COUNT(*) AS row_count,
         COUNTIF(dc_id IS NULL) AS null_key_count,
         COUNT(*) - COUNT(DISTINCT dc_id) AS duplicate_key_count
  FROM sfs_demo.distribution_centers
  UNION ALL
  SELECT '2_suppliers', COUNT(*), COUNTIF(supplier_id IS NULL), COUNT(*) - COUNT(DISTINCT supplier_id)
  FROM sfs_demo.suppliers
  UNION ALL
  SELECT '3_products', COUNT(*), COUNTIF(sku IS NULL), COUNT(*) - COUNT(DISTINCT sku)
  FROM sfs_demo.products
  UNION ALL
  SELECT '4_customers', COUNT(*), COUNTIF(customer_id IS NULL), COUNT(*) - COUNT(DISTINCT customer_id)
  FROM sfs_demo.customers
  UNION ALL
  SELECT '5_customer_contacts', COUNT(*), COUNTIF(contact_id IS NULL OR customer_id IS NULL), COUNT(*) - COUNT(DISTINCT contact_id)
  FROM sfs_demo.customer_contacts
  UNION ALL
  SELECT '6_purchase_orders', COUNT(*), COUNTIF(po_id IS NULL OR supplier_id IS NULL OR dc_id IS NULL), COUNT(*) - COUNT(DISTINCT po_id)
  FROM sfs_demo.purchase_orders
  UNION ALL
  SELECT '7_po_lines', COUNT(*), COUNTIF(po_line_id IS NULL OR po_id IS NULL OR sku IS NULL OR order_date IS NULL), COUNT(*) - COUNT(DISTINCT po_line_id)
  FROM sfs_demo.po_lines
  UNION ALL
  SELECT '8_accounts_payable', COUNT(*), COUNTIF(remittance_id IS NULL OR po_id IS NULL OR supplier_id IS NULL), COUNT(*) - COUNT(DISTINCT remittance_id)
  FROM sfs_demo.accounts_payable
  UNION ALL
  SELECT '9_inventory_snapshots', COUNT(*),
         COUNTIF(snapshot_date IS NULL OR dc_id IS NULL OR sku IS NULL),
         COUNT(*) - COUNT(DISTINCT CONCAT(CAST(snapshot_date AS STRING), '|', dc_id, '|', sku))
  FROM sfs_demo.inventory_snapshots
  UNION ALL
  SELECT '10_orders', COUNT(*), COUNTIF(order_id IS NULL OR customer_id IS NULL OR dc_id IS NULL), COUNT(*) - COUNT(DISTINCT order_id)
  FROM sfs_demo.orders
  UNION ALL
  SELECT '11_order_lines', COUNT(*), COUNTIF(order_line_id IS NULL OR order_id IS NULL OR sku IS NULL OR order_date IS NULL), COUNT(*) - COUNT(DISTINCT order_line_id)
  FROM sfs_demo.order_lines
  UNION ALL
  SELECT '12_shipments', COUNT(*), COUNTIF(shipment_id IS NULL OR order_id IS NULL OR dc_id IS NULL OR customer_id IS NULL), COUNT(*) - COUNT(DISTINCT shipment_id)
  FROM sfs_demo.shipments
)
ORDER BY row_count DESC;

-- -----------------------------------------------------------------------------
-- 2. Referential Integrity Checks (No Orphan order_lines, po_lines, contacts, etc.)
-- -----------------------------------------------------------------------------
SELECT check_name, orphan_count FROM (
  SELECT 'order_lines -> orders (order_id)' AS check_name,
         COUNT(*) AS orphan_count
  FROM sfs_demo.order_lines ol
  LEFT JOIN sfs_demo.orders o ON ol.order_id = o.order_id
  WHERE o.order_id IS NULL

  UNION ALL
  SELECT 'order_lines -> products (sku)',
         COUNT(*)
  FROM sfs_demo.order_lines ol
  LEFT JOIN sfs_demo.products p ON ol.sku = p.sku
  WHERE p.sku IS NULL

  UNION ALL
  SELECT 'order_lines -> products (substituted_sku)',
         COUNT(*)
  FROM sfs_demo.order_lines ol
  LEFT JOIN sfs_demo.products p ON ol.substituted_sku = p.sku
  WHERE ol.substituted_sku IS NOT NULL AND p.sku IS NULL

  UNION ALL
  SELECT 'order_lines -> distribution_centers (dc_id)',
         COUNT(*)
  FROM sfs_demo.order_lines ol
  LEFT JOIN sfs_demo.distribution_centers dc ON ol.dc_id = dc.dc_id
  WHERE dc.dc_id IS NULL

  UNION ALL
  SELECT 'order_lines -> customers (customer_id)',
         COUNT(*)
  FROM sfs_demo.order_lines ol
  LEFT JOIN sfs_demo.customers c ON ol.customer_id = c.customer_id
  WHERE c.customer_id IS NULL

  UNION ALL
  SELECT 'po_lines -> purchase_orders (po_id)',
         COUNT(*)
  FROM sfs_demo.po_lines pol
  LEFT JOIN sfs_demo.purchase_orders po ON pol.po_id = po.po_id
  WHERE po.po_id IS NULL

  UNION ALL
  SELECT 'po_lines -> products (sku)',
         COUNT(*)
  FROM sfs_demo.po_lines pol
  LEFT JOIN sfs_demo.products p ON pol.sku = p.sku
  WHERE p.sku IS NULL

  UNION ALL
  SELECT 'po_lines -> distribution_centers (dc_id)',
         COUNT(*)
  FROM sfs_demo.po_lines pol
  LEFT JOIN sfs_demo.distribution_centers dc ON pol.dc_id = dc.dc_id
  WHERE dc.dc_id IS NULL

  UNION ALL
  SELECT 'customer_contacts -> customers (customer_id)',
         COUNT(*)
  FROM sfs_demo.customer_contacts ct
  LEFT JOIN sfs_demo.customers c ON ct.customer_id = c.customer_id
  WHERE c.customer_id IS NULL

  UNION ALL
  SELECT 'orders -> customers (customer_id)',
         COUNT(*)
  FROM sfs_demo.orders o
  LEFT JOIN sfs_demo.customers c ON o.customer_id = c.customer_id
  WHERE c.customer_id IS NULL

  UNION ALL
  SELECT 'shipments -> orders (order_id)',
         COUNT(*)
  FROM sfs_demo.shipments s
  LEFT JOIN sfs_demo.orders o ON s.order_id = o.order_id
  WHERE o.order_id IS NULL
)
ORDER BY check_name;

-- -----------------------------------------------------------------------------
-- 3. Planted Pattern 1: Two Suppliers with Severe Final-Quarter Lead-Time Degradation
-- -----------------------------------------------------------------------------
WITH supplier_perf AS (
  SELECT
    s.supplier_id,
    s.name AS supplier_name,
    s.primary_category,
    s.contracted_lead_time_days,
    ROUND(AVG(IF(po.order_date < DATE '2026-07-01', po.actual_lead_time_days, NULL)), 2) AS avg_lead_q1_q5_days,
    ROUND(AVG(IF(po.order_date >= DATE '2026-07-01', po.actual_lead_time_days, NULL)), 2) AS avg_lead_q6_days,
    ROUND(
      100.0 * (
        AVG(IF(po.order_date >= DATE '2026-07-01', po.actual_lead_time_days, NULL))
        / AVG(IF(po.order_date < DATE '2026-07-01', po.actual_lead_time_days, NULL)) - 1.0
      ),
      1
    ) AS lead_time_pct_increase,
    ROUND(
      100.0 * COUNTIF(po.order_date >= DATE '2026-07-01' AND po.status = 'LATE_RECEIVED')
      / NULLIF(COUNTIF(po.order_date >= DATE '2026-07-01'), 0),
      1
    ) AS q6_late_po_pct
  FROM sfs_demo.suppliers s
  JOIN sfs_demo.purchase_orders po ON s.supplier_id = po.supplier_id
  GROUP BY 1, 2, 3, 4
)
SELECT *
FROM supplier_perf
ORDER BY lead_time_pct_increase DESC
LIMIT 10;

-- -----------------------------------------------------------------------------
-- 4. Planted Pattern 2: Seasonality (Produce Summer Spike & Protein Holiday Spike)
-- -----------------------------------------------------------------------------
WITH monthly_cat AS (
  SELECT
    p.category,
    FORMAT_DATE('%Y-%m', ol.order_date) AS year_month,
    EXTRACT(MONTH FROM ol.order_date) AS cal_month,
    SUM(ol.ordered_cases) AS monthly_ordered_cases
  FROM sfs_demo.order_lines ol
  JOIN sfs_demo.products p ON ol.sku = p.sku
  GROUP BY 1, 2, 3
)
SELECT
  category,
  ROUND(AVG(IF(cal_month IN (6, 7, 8), monthly_ordered_cases, NULL)), 0) AS summer_jun_aug_avg_cases,
  ROUND(AVG(IF(cal_month NOT IN (6, 7, 8), monthly_ordered_cases, NULL)), 0) AS non_summer_avg_cases,
  ROUND(
    AVG(IF(cal_month IN (6, 7, 8), monthly_ordered_cases, NULL))
    / AVG(IF(cal_month NOT IN (6, 7, 8), monthly_ordered_cases, NULL)),
    2
  ) AS summer_vs_nonsummer_lift,
  ROUND(AVG(IF(cal_month IN (11, 12), monthly_ordered_cases, NULL)), 0) AS holiday_nov_dec_avg_cases,
  ROUND(AVG(IF(cal_month NOT IN (11, 12), monthly_ordered_cases, NULL)), 0) AS non_holiday_avg_cases,
  ROUND(
    AVG(IF(cal_month IN (11, 12), monthly_ordered_cases, NULL))
    / AVG(IF(cal_month NOT IN (11, 12), monthly_ordered_cases, NULL)),
    2
  ) AS holiday_vs_nonholiday_lift
FROM monthly_cat
GROUP BY category
ORDER BY GREATEST(summer_vs_nonsummer_lift, holiday_vs_nonholiday_lift) DESC;

-- -----------------------------------------------------------------------------
-- 5. Planted Pattern 3: Low-Fill-Rate Distribution Center (DC-SE-01 Atlanta)
-- -----------------------------------------------------------------------------
WITH dc_orders AS (
  SELECT
    dc_id,
    COUNT(*) AS total_orders,
    SUM(ordered_cases) AS ordered_cases,
    SUM(shipped_cases) AS shipped_cases,
    ROUND(100.0 * SUM(shipped_cases) / SUM(ordered_cases), 2) AS case_fill_rate_pct,
    ROUND(100.0 * COUNTIF(order_status = 'SHORT_SHIPPED') / COUNT(*), 2) AS short_shipped_orders_pct
  FROM sfs_demo.orders
  GROUP BY dc_id
),
dc_inv AS (
  SELECT
    dc_id,
    ROUND(100.0 * COUNTIF(on_hand_cases = 0) / COUNT(*), 2) AS snapshot_stockout_rate_pct,
    ROUND(AVG(days_of_supply), 2) AS avg_days_of_supply
  FROM sfs_demo.inventory_snapshots
  GROUP BY dc_id
)
SELECT
  dc.dc_id,
  dc.city,
  dc.region,
  o.total_orders,
  o.ordered_cases,
  o.shipped_cases,
  o.case_fill_rate_pct,
  o.short_shipped_orders_pct,
  i.snapshot_stockout_rate_pct,
  i.avg_days_of_supply
FROM sfs_demo.distribution_centers dc
JOIN dc_orders o ON dc.dc_id = o.dc_id
JOIN dc_inv i ON dc.dc_id = i.dc_id
ORDER BY o.case_fill_rate_pct ASC;

-- -----------------------------------------------------------------------------
-- 6. Planted Pattern 4: Cold-Chain Temperature Excursion Route (RTE-SW-404)
-- -----------------------------------------------------------------------------
SELECT
  route_id,
  dc_id,
  COUNT(*) AS cold_chain_loads,
  COUNTIF(temperature_excursion) AS excursion_loads,
  ROUND(100.0 * COUNTIF(temperature_excursion) / COUNT(*), 2) AS excursion_rate_pct,
  ROUND(AVG(IF(temperature_excursion, peak_temp_f, NULL)), 1) AS avg_excursion_peak_temp_f
FROM sfs_demo.shipments
WHERE load_temp_zone IN ('refrigerated', 'frozen')
GROUP BY route_id, dc_id
ORDER BY excursion_rate_pct DESC
LIMIT 10;

-- -----------------------------------------------------------------------------
-- 7. Planted Pattern 5: Churn-Risk Customers (Sharp Final 8-Week Order Drop)
-- -----------------------------------------------------------------------------
WITH customer_windows AS (
  SELECT
    c.customer_id,
    c.operator_name,
    c.segment,
    c.assigned_dc_id,
    ROUND(SUM(IF(o.order_date < DATE '2026-08-06', o.ordered_cases, 0)) / (492.0 / 7.0), 1) AS baseline_70wk_cases_per_wk,
    ROUND(SUM(IF(o.order_date >= DATE '2026-08-06', o.ordered_cases, 0)) / (56.0 / 7.0), 1) AS final_8wk_cases_per_wk
  FROM sfs_demo.customers c
  LEFT JOIN sfs_demo.orders o ON c.customer_id = o.customer_id
  GROUP BY 1, 2, 3, 4
)
SELECT
  customer_id,
  operator_name,
  segment,
  assigned_dc_id,
  baseline_70wk_cases_per_wk,
  final_8wk_cases_per_wk,
  ROUND(100.0 * (final_8wk_cases_per_wk / NULLIF(baseline_70wk_cases_per_wk, 0) - 1.0), 1) AS pct_change
FROM customer_windows
ORDER BY pct_change ASC
LIMIT 20;
