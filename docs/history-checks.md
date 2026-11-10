> Historical milestone. The local application now integrates upload, retrieval, review and approval; see [current implementation](local-application.md). Scores and limitations below describe the original experiment.

# Checking previous invoices and orders

A purchase order is the buyer's agreement to buy something. An invoice is the seller's bill. An approval records how much of that agreement has been consumed; it does not send payment.

The internal history service now uses PostgreSQL to answer:

1. Has this exact file appeared before? Compare its SHA-256 fingerprint.
2. Has this vendor used the same invoice number? Retrieve candidates and distinguish exact numbers, changed amounts (possible revisions), and normalized identifier collisions. Another vendor's identical number alone is not a duplicate. Rejected candidates remain visible but do not block a new approval.
3. How much is left on the order? Sum actual approved allocations. Pending/rejected invoices do not consume the balance.
4. Have we bought something similar? SQL retrieves up to 100 lines from this vendor's previous orders; lexical TF-IDF ranks their descriptions. Suggestions never authorize an invoice, and a closed historical order is not a valid current order.

Approval locks the relevant vendor/order/invoice/order lines inside one PostgreSQL transaction, checks current state, groups multiple invoice rows consuming the same order line, and writes each allocation once. Competing approvals see the balance after the first transaction commits. An invoice already approved returns its original approval instead of consuming quantity again.

## Run the fictional example

After `docker compose up --build -d`:

```sh
docker compose exec -T app python -m reconcile.history_demo --seed
docker compose exec -T app python -m reconcile.history_demo --approve-current
docker compose exec -T app python -m reconcile.history_demo --approve-current
```

This explicitly creates/migrates a separate `reconcile_history_demo` schema containing fictional records. Seed is repeatable and never resets existing records. The first run starts with 1,000 gloves ordered and 400 already approved, leaving 600. Approving the next 600 leaves zero. Repeating that approval leaves zero and returns `already_approved`.

The JSON output includes previous orders, duplicate candidates, and balances. These are seeded data, **not** a live PDF extraction result. The seed function supplies a trusted ready recommendation solely for this database demonstration.

## Tests

```sh
make test
docker compose exec -T app python < backend/tests/test_history_postgres.py
```

The second command runs real PostgreSQL tests in fresh, randomly named test schemas and deletes only those schemas afterwards. It exercises migrations twice, schema agreement, partial billing, overage, concurrent approvals, retries, vendor-scoped history, duplicate detection, identifier collisions, order-balance protection, and state checks. Local `make test` skips the database suite unless `HISTORY_TEST_DATABASE_URL` is explicitly supplied; skips are not passes.

The migration currently contains only the procurement/history subset. Full extraction/evidence/run/job/auth schema remains outstanding. Do not use this internal approval service as a complete financial validator: it trusts a previously verified decision, uses exact-price checks initially, and does not yet implement tax/arithmetic/date validation, full correction audit, configurable tolerance, or durable request-idempotency records. There is no public approval endpoint yet. API routes remain locked until staff authentication and the complete pipeline exist.
