# Unified workspace source contract

The former multi-stage roadmap is consolidated in [Delivery](DELIVERY.md). Current design and lineage are defined in [Architecture](ARCHITECTURE.md).

E-Commerce and the independent [Greenweez project](../integrations/greenweez/README.md) share repository tooling and presentation components. They do not share customers, orders, currency assumptions or financial totals. Olist notebooks and GA4 lab events remain independent populations.

Source states remain `missing`, `invalid`, `synthetic`, `external_unverified`, `api_snapshot` and `api_empty` as defined by the adapters. Missing inputs are not zero trading activity; an external snapshot is not self-certified business evidence.

Public website and Power BI builders accept only the two synthetic dbt sources. The private Streamlit workspace retains independently scoped source tabs. Keep source hashes, extraction time and metric definitions alongside any future real-source reconciliation.
