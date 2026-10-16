# Stark Food Services (SFS)

Stark Food Services (SFS) is a fictional US broadline foodservice distributor. This repository generates realistic, deterministic synthetic supply-chain data (18 months of history across products, suppliers, distribution centers, customers, contacts, accounts payable, purchase orders, daily inventory snapshots, customer orders, and shipments), defines the BigQuery schema DDL, and provides automated data-quality and referential-integrity validation.

## Quick Start

```bash
make venv
make generate
make validate
```
