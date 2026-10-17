-- Stark Food Services (SFS) — BigQuery Schema DDL
-- Dataset: sfs_demo (project-agnostic; never hardcode project IDs in tracked files)

CREATE SCHEMA IF NOT EXISTS sfs_demo
OPTIONS (
  location = 'US',
  description = 'Stark Food Services (SFS) synthetic broadline foodservice supply-chain dataset'
);

-- 1. Suppliers
CREATE OR REPLACE TABLE sfs_demo.suppliers (
  supplier_id STRING NOT NULL OPTIONS (description = 'Unique supplier identifier (e.g., SUP-001)'),
  name STRING NOT NULL OPTIONS (description = 'Legal or trade name of the foodservice supplier'),
  region STRING NOT NULL OPTIONS (description = 'US geographic region of supplier primary operations'),
  primary_category STRING NOT NULL OPTIONS (description = 'Primary product category supplied'),
  contracted_lead_time_days INT64 NOT NULL OPTIONS (description = 'Contracted replenishment lead time in calendar days'),
  reliability_profile STRING NOT NULL OPTIONS (description = 'Reliability tier (tier_1_reliable, standard, variable, degrading_last_quarter)'),
  baseline_on_time_rate FLOAT64 NOT NULL OPTIONS (description = 'Historical baseline on-time delivery probability (0.0 to 1.0)'),
  PRIMARY KEY (supplier_id) NOT ENFORCED
)
OPTIONS (
  description = 'Foodservice product manufacturers, growers, and processors supplying SFS distribution centers'
);

-- 2. Distribution Centers
CREATE OR REPLACE TABLE sfs_demo.distribution_centers (
  dc_id STRING NOT NULL OPTIONS (description = 'Unique distribution center identifier (e.g., DC-NE-01)'),
  name STRING NOT NULL OPTIONS (description = 'Distribution center facility name'),
  city STRING NOT NULL OPTIONS (description = 'Facility city'),
  state STRING NOT NULL OPTIONS (description = 'Facility two-letter US state code'),
  region STRING NOT NULL OPTIONS (description = 'US geographic region served by the DC'),
  capacity_cases INT64 NOT NULL OPTIONS (description = 'Total storage capacity in cases across all temperature zones'),
  cold_storage_capacity_cases INT64 NOT NULL OPTIONS (description = 'Refrigerated and frozen storage capacity in cases'),
  PRIMARY KEY (dc_id) NOT ENFORCED
)
OPTIONS (
  description = 'Regional broadline distribution centers operated by Stark Food Services'
);

-- 3. Products
CREATE OR REPLACE TABLE sfs_demo.products (
  sku STRING NOT NULL OPTIONS (description = 'Unique stock keeping unit identifier (e.g., SKU-10001)'),
  description STRING NOT NULL OPTIONS (description = 'Commercial product description'),
  category STRING NOT NULL OPTIONS (description = 'Product category: produce, protein, dairy, dry, frozen, paper, chemical'),
  brand STRING NOT NULL OPTIONS (description = 'National or SFS private-label brand name'),
  pack_size STRING NOT NULL OPTIONS (description = 'Standard foodservice case pack configuration (e.g., 6/10#, 4/5 lb)'),
  case_cost NUMERIC(10, 2) NOT NULL OPTIONS (description = 'Distributor wholesale acquisition cost per case in USD'),
  list_price NUMERIC(10, 2) NOT NULL OPTIONS (description = 'Standard operator list price per case in USD'),
  temp_zone STRING NOT NULL OPTIONS (description = 'Required storage/transport temperature zone: ambient, refrigerated, frozen'),
  shelf_life_days INT64 NOT NULL OPTIONS (description = 'Expected shelf life in days from receipt'),
  primary_supplier_id STRING NOT NULL OPTIONS (description = 'Primary replenishment supplier ID'),
  substitute_sku STRING OPTIONS (description = 'Designated substitute SKU within the same category when out of stock'),
  PRIMARY KEY (sku) NOT ENFORCED,
  FOREIGN KEY (primary_supplier_id) REFERENCES sfs_demo.suppliers(supplier_id) NOT ENFORCED
)
CLUSTER BY sku, category, temp_zone
OPTIONS (
  description = 'Master catalog of ~600 foodservice SKUs across 7 categories and 3 temperature zones'
);

-- 4. Customers
CREATE OR REPLACE TABLE sfs_demo.customers (
  customer_id STRING NOT NULL OPTIONS (description = 'Unique customer account identifier (e.g., CUST-0001)'),
  operator_name STRING NOT NULL OPTIONS (description = 'Foodservice operator business or institution name'),
  segment STRING NOT NULL OPTIONS (description = 'Customer market segment: restaurant, healthcare, education, hospitality'),
  region STRING NOT NULL OPTIONS (description = 'Customer geographic region'),
  credit_terms STRING NOT NULL OPTIONS (description = 'Contracted payment terms (Net 15, Net 30, Net 45, COD)'),
  assigned_dc_id STRING NOT NULL OPTIONS (description = 'Primary servicing SFS distribution center ID'),
  account_open_date DATE NOT NULL OPTIONS (description = 'Date the operator account was established'),
  PRIMARY KEY (customer_id) NOT ENFORCED,
  FOREIGN KEY (assigned_dc_id) REFERENCES sfs_demo.distribution_centers(dc_id) NOT ENFORCED
)
CLUSTER BY assigned_dc_id, customer_id, segment
OPTIONS (
  description = 'Foodservice operator customer accounts serviced by SFS'
);

-- 5. Customer Contacts (PII-bearing)
CREATE OR REPLACE TABLE sfs_demo.customer_contacts (
  contact_id STRING NOT NULL OPTIONS (description = 'Unique contact record identifier (e.g., CONT-00001)'),
  customer_id STRING NOT NULL OPTIONS (description = 'Associated customer account ID'),
  name STRING NOT NULL OPTIONS (description = 'PII: Full name of the customer contact'),
  email STRING NOT NULL OPTIONS (description = 'PII: Direct email address of the contact'),
  phone STRING NOT NULL OPTIONS (description = 'PII: Direct telephone number of the contact'),
  role STRING NOT NULL OPTIONS (description = 'Job role (Executive Chef, Kitchen Manager, Purchasing Director, AP Lead, GM)'),
  is_primary BOOL NOT NULL OPTIONS (description = 'Whether this contact is the primary account contact'),
  PRIMARY KEY (contact_id) NOT ENFORCED,
  FOREIGN KEY (customer_id) REFERENCES sfs_demo.customers(customer_id) NOT ENFORCED
)
CLUSTER BY customer_id
OPTIONS (
  description = 'PII-bearing customer contact directory for data governance and masking demonstrations'
);

-- 6. Purchase Orders (Supplier -> DC Replenishment Header)
CREATE OR REPLACE TABLE sfs_demo.purchase_orders (
  po_id STRING NOT NULL OPTIONS (description = 'Unique purchase order identifier (e.g., PO-000001)'),
  supplier_id STRING NOT NULL OPTIONS (description = 'Replenishment supplier ID'),
  dc_id STRING NOT NULL OPTIONS (description = 'Receiving SFS distribution center ID'),
  order_date DATE NOT NULL OPTIONS (description = 'Date PO was issued to supplier'),
  expected_delivery_date DATE NOT NULL OPTIONS (description = 'Scheduled delivery date based on contracted lead time'),
  actual_delivery_date DATE NOT NULL OPTIONS (description = 'Actual date shipment was received at the DC dock'),
  contracted_lead_time_days INT64 NOT NULL OPTIONS (description = 'Contracted lead time in days at time of PO'),
  actual_lead_time_days INT64 NOT NULL OPTIONS (description = 'Actual elapsed lead time in calendar days'),
  status STRING NOT NULL OPTIONS (description = 'Receipt status: RECEIVED, LATE_RECEIVED, PARTIAL'),
  total_ordered_cases INT64 NOT NULL OPTIONS (description = 'Total cases ordered across all lines on the PO'),
  total_received_cases INT64 NOT NULL OPTIONS (description = 'Total cases received across all lines on the PO'),
  total_cost NUMERIC(12, 2) NOT NULL OPTIONS (description = 'Total landed cost of received cases in USD'),
  PRIMARY KEY (po_id) NOT ENFORCED,
  FOREIGN KEY (supplier_id) REFERENCES sfs_demo.suppliers(supplier_id) NOT ENFORCED,
  FOREIGN KEY (dc_id) REFERENCES sfs_demo.distribution_centers(dc_id) NOT ENFORCED
)
PARTITION BY order_date
CLUSTER BY dc_id, supplier_id
OPTIONS (
  description = 'Inbound replenishment purchase orders from suppliers to SFS distribution centers'
);

-- 7. Purchase Order Lines
CREATE OR REPLACE TABLE sfs_demo.po_lines (
  po_line_id STRING NOT NULL OPTIONS (description = 'Unique purchase order line identifier (e.g., POL-0000001)'),
  po_id STRING NOT NULL OPTIONS (description = 'Parent purchase order ID'),
  order_date DATE NOT NULL OPTIONS (description = 'Date parent PO was issued to supplier'),
  dc_id STRING NOT NULL OPTIONS (description = 'Receiving SFS distribution center ID'),
  line_number INT64 NOT NULL OPTIONS (description = 'Sequential line number within the PO'),
  sku STRING NOT NULL OPTIONS (description = 'Replenished product SKU'),
  ordered_cases INT64 NOT NULL OPTIONS (description = 'Cases ordered on this PO line'),
  received_cases INT64 NOT NULL OPTIONS (description = 'Cases actually received at the DC'),
  case_cost NUMERIC(10, 2) NOT NULL OPTIONS (description = 'Unit wholesale cost per case in USD'),
  line_cost NUMERIC(12, 2) NOT NULL OPTIONS (description = 'Extended cost for received cases in USD'),
  PRIMARY KEY (po_line_id) NOT ENFORCED,
  FOREIGN KEY (po_id) REFERENCES sfs_demo.purchase_orders(po_id) NOT ENFORCED,
  FOREIGN KEY (dc_id) REFERENCES sfs_demo.distribution_centers(dc_id) NOT ENFORCED,
  FOREIGN KEY (sku) REFERENCES sfs_demo.products(sku) NOT ENFORCED
)
PARTITION BY order_date
CLUSTER BY dc_id, sku
OPTIONS (
  description = 'Line-item detail for inbound supplier purchase orders'
);

-- 8. Accounts Payable (Sensitive financial / remittance records)
CREATE OR REPLACE TABLE sfs_demo.accounts_payable (
  remittance_id STRING NOT NULL OPTIONS (description = 'Unique AP remittance identifier (e.g., AP-000001)'),
  po_id STRING NOT NULL OPTIONS (description = 'Associated purchase order ID'),
  supplier_id STRING NOT NULL OPTIONS (description = 'Payee supplier ID'),
  invoice_number STRING NOT NULL OPTIONS (description = 'Supplier invoice reference number'),
  invoice_date DATE NOT NULL OPTIONS (description = 'Invoice issue date (typically actual receipt date)'),
  payment_date DATE NOT NULL OPTIONS (description = 'Date electronic remittance was disbursed'),
  payment_amount NUMERIC(12, 2) NOT NULL OPTIONS (description = 'Total USD amount remitted to supplier'),
  payment_method STRING NOT NULL OPTIONS (description = 'Disbursement method: ACH, WIRE, EFT'),
  bank_name STRING NOT NULL OPTIONS (description = 'SENSITIVE: Receiving financial institution name'),
  aba_routing_number STRING NOT NULL OPTIONS (description = 'SENSITIVE: 9-digit US ABA bank routing number'),
  bank_account_number STRING NOT NULL OPTIONS (description = 'SENSITIVE: Unmasked receiving bank account number'),
  supplier_tax_id STRING NOT NULL OPTIONS (description = 'SENSITIVE: Supplier federal EIN / tax identification number'),
  remittance_email STRING NOT NULL OPTIONS (description = 'SENSITIVE: Supplier treasury/AP remittance advice email'),
  PRIMARY KEY (remittance_id) NOT ENFORCED,
  FOREIGN KEY (po_id) REFERENCES sfs_demo.purchase_orders(po_id) NOT ENFORCED,
  FOREIGN KEY (supplier_id) REFERENCES sfs_demo.suppliers(supplier_id) NOT ENFORCED
)
PARTITION BY payment_date
CLUSTER BY supplier_id
OPTIONS (
  description = 'Sensitive supplier remittance and banking records for column-level security and DLP demos'
);

-- 9. Inventory Snapshots (Daily DC x SKU position)
CREATE OR REPLACE TABLE sfs_demo.inventory_snapshots (
  snapshot_date DATE NOT NULL OPTIONS (description = 'Calendar date of end-of-day inventory snapshot'),
  dc_id STRING NOT NULL OPTIONS (description = 'Distribution center ID'),
  sku STRING NOT NULL OPTIONS (description = 'Product SKU'),
  on_hand_cases INT64 NOT NULL OPTIONS (description = 'Physical cases available on hand at end of day'),
  safety_stock INT64 NOT NULL OPTIONS (description = 'Target minimum safety stock buffer in cases'),
  days_of_supply FLOAT64 NOT NULL OPTIONS (description = 'Estimated days of supply based on trailing daily demand rate'),
  PRIMARY KEY (snapshot_date, dc_id, sku) NOT ENFORCED,
  FOREIGN KEY (dc_id) REFERENCES sfs_demo.distribution_centers(dc_id) NOT ENFORCED,
  FOREIGN KEY (sku) REFERENCES sfs_demo.products(sku) NOT ENFORCED
)
PARTITION BY snapshot_date
CLUSTER BY dc_id, sku
OPTIONS (
  description = 'Daily DC x SKU inventory position, safety stock targets, and days of supply'
);

-- 10. Customer Orders (Header)
CREATE OR REPLACE TABLE sfs_demo.orders (
  order_id STRING NOT NULL OPTIONS (description = 'Unique customer sales order identifier (e.g., ORD-0000001)'),
  customer_id STRING NOT NULL OPTIONS (description = 'Ordering customer account ID'),
  dc_id STRING NOT NULL OPTIONS (description = 'Fulfilling SFS distribution center ID'),
  order_date DATE NOT NULL OPTIONS (description = 'Date customer placed the order'),
  scheduled_delivery_date DATE NOT NULL OPTIONS (description = 'Scheduled customer delivery date'),
  order_status STRING NOT NULL OPTIONS (description = 'Fulfillment summary status: FILLED, SHORT_SHIPPED'),
  ordered_cases INT64 NOT NULL OPTIONS (description = 'Total cases ordered across all lines'),
  shipped_cases INT64 NOT NULL OPTIONS (description = 'Total cases shipped (including approved substitutions)'),
  case_fill_rate FLOAT64 NOT NULL OPTIONS (description = 'Order-level case fill ratio (shipped_cases / ordered_cases)'),
  order_total NUMERIC(12, 2) NOT NULL OPTIONS (description = 'Total invoiced order amount in USD for shipped cases'),
  PRIMARY KEY (order_id) NOT ENFORCED,
  FOREIGN KEY (customer_id) REFERENCES sfs_demo.customers(customer_id) NOT ENFORCED,
  FOREIGN KEY (dc_id) REFERENCES sfs_demo.distribution_centers(dc_id) NOT ENFORCED
)
PARTITION BY order_date
CLUSTER BY dc_id, customer_id
OPTIONS (
  description = 'Customer outbound foodservice order headers'
);

-- 11. Customer Order Lines
CREATE OR REPLACE TABLE sfs_demo.order_lines (
  order_line_id STRING NOT NULL OPTIONS (description = 'Unique customer order line identifier (e.g., OL-0000001)'),
  order_id STRING NOT NULL OPTIONS (description = 'Parent customer order ID'),
  order_date DATE NOT NULL OPTIONS (description = 'Date customer placed the parent order'),
  dc_id STRING NOT NULL OPTIONS (description = 'Fulfilling SFS distribution center ID'),
  customer_id STRING NOT NULL OPTIONS (description = 'Ordering customer account ID'),
  line_number INT64 NOT NULL OPTIONS (description = 'Sequential line number within the order'),
  sku STRING NOT NULL OPTIONS (description = 'Originally ordered product SKU'),
  ordered_cases INT64 NOT NULL OPTIONS (description = 'Number of cases requested by customer'),
  shipped_cases INT64 NOT NULL OPTIONS (description = 'Number of cases actually shipped to customer'),
  fill_status STRING NOT NULL OPTIONS (description = 'Line fulfillment outcome: FILLED, PARTIAL, OUT_OF_STOCK, SUBSTITUTED'),
  substituted_sku STRING OPTIONS (description = 'Replacement SKU shipped when fill_status is SUBSTITUTED (NULL otherwise)'),
  unit_price NUMERIC(10, 2) NOT NULL OPTIONS (description = 'Billed price per case in USD'),
  line_total NUMERIC(12, 2) NOT NULL OPTIONS (description = 'Extended line total in USD (shipped_cases * unit_price)'),
  PRIMARY KEY (order_line_id) NOT ENFORCED,
  FOREIGN KEY (order_id) REFERENCES sfs_demo.orders(order_id) NOT ENFORCED,
  FOREIGN KEY (dc_id) REFERENCES sfs_demo.distribution_centers(dc_id) NOT ENFORCED,
  FOREIGN KEY (customer_id) REFERENCES sfs_demo.customers(customer_id) NOT ENFORCED,
  FOREIGN KEY (sku) REFERENCES sfs_demo.products(sku) NOT ENFORCED,
  FOREIGN KEY (substituted_sku) REFERENCES sfs_demo.products(sku) NOT ENFORCED
)
PARTITION BY order_date
CLUSTER BY dc_id, sku, customer_id
OPTIONS (
  description = 'Customer order line items (~250k rows) tracking ordered vs. shipped cases, OOS, and substitutions'
);

-- 12. Shipments (Outbound Route & Cold-Chain Telemetry)
CREATE OR REPLACE TABLE sfs_demo.shipments (
  shipment_id STRING NOT NULL OPTIONS (description = 'Unique outbound shipment identifier (e.g., SHP-0000001)'),
  order_id STRING NOT NULL OPTIONS (description = 'Fulfilled customer order ID'),
  dc_id STRING NOT NULL OPTIONS (description = 'Origin SFS distribution center ID'),
  customer_id STRING NOT NULL OPTIONS (description = 'Destination customer account ID'),
  route_id STRING NOT NULL OPTIONS (description = 'Assigned delivery route identifier (e.g., RTE-SW-404)'),
  load_temp_zone STRING NOT NULL OPTIONS (description = 'Most stringent temperature zone on load: ambient, refrigerated, frozen'),
  scheduled_delivery TIMESTAMP NOT NULL OPTIONS (description = 'Scheduled delivery appointment timestamp (UTC)'),
  actual_delivery TIMESTAMP NOT NULL OPTIONS (description = 'Actual dock arrival timestamp (UTC)'),
  on_time BOOL NOT NULL OPTIONS (description = 'True if actual_delivery is within 30 minutes of scheduled_delivery'),
  temperature_excursion BOOL OPTIONS (description = 'For refrigerated/frozen loads, True if reefer temp exceeded threshold; NULL for ambient loads'),
  peak_temp_f FLOAT64 OPTIONS (description = 'Peak compartment temperature (°F) recorded during transit for cold-chain loads; NULL for ambient'),
  PRIMARY KEY (shipment_id) NOT ENFORCED,
  FOREIGN KEY (order_id) REFERENCES sfs_demo.orders(order_id) NOT ENFORCED,
  FOREIGN KEY (dc_id) REFERENCES sfs_demo.distribution_centers(dc_id) NOT ENFORCED,
  FOREIGN KEY (customer_id) REFERENCES sfs_demo.customers(customer_id) NOT ENFORCED
)
PARTITION BY DATE(scheduled_delivery)
CLUSTER BY dc_id, customer_id, route_id
OPTIONS (
  description = 'Outbound delivery shipments with route assignment, on-time performance, and cold-chain excursion flags'
);


-- 13. Replenishment Drafts (Append-only write table for MCP agent actions)
CREATE TABLE IF NOT EXISTS sfs_demo.replenishment_drafts (
  draft_id STRING NOT NULL OPTIONS (description = 'Unique replenishment draft identifier (UUID)'),
  created_at TIMESTAMP NOT NULL OPTIONS (description = 'UTC timestamp when the replenishment draft was created'),
  dc_id STRING NOT NULL OPTIONS (description = 'Target SFS distribution center ID'),
  sku STRING NOT NULL OPTIONS (description = 'Product SKU requested for replenishment'),
  cases_requested INT64 NOT NULL OPTIONS (description = 'Number of cases requested for replenishment'),
  rationale STRING NOT NULL OPTIONS (description = 'Analytical rationale or agent justification for the draft PO'),
  created_by STRING NOT NULL OPTIONS (description = 'Identity of the agent or workflow that created the draft'),
  PRIMARY KEY (draft_id) NOT ENFORCED
)
PARTITION BY DATE(created_at)
CLUSTER BY dc_id, sku
OPTIONS (
  description = 'Append-only staging table for AI agent replenishment draft requests'
);

-- 14. Customer Flags (Append-only write table for MCP agent outreach actions)
CREATE TABLE IF NOT EXISTS sfs_demo.customer_flags (
  flag_id STRING NOT NULL OPTIONS (description = 'Unique customer outreach flag identifier (UUID)'),
  created_at TIMESTAMP NOT NULL OPTIONS (description = 'UTC timestamp when the customer flag was recorded'),
  customer_id STRING NOT NULL OPTIONS (description = 'Flagged customer account ID'),
  flag_type STRING NOT NULL OPTIONS (description = 'Outreach flag category (e.g., CHURN_RISK, SERVICE_RECOVERY)'),
  note STRING NOT NULL OPTIONS (description = 'Actionable context note for account management outreach'),
  created_by STRING NOT NULL OPTIONS (description = 'Identity of the agent or workflow that recorded the flag'),
  PRIMARY KEY (flag_id) NOT ENFORCED
)
PARTITION BY DATE(created_at)
CLUSTER BY customer_id, flag_type
OPTIONS (
  description = 'Append-only staging table for AI agent customer retention and outreach flags'
);
