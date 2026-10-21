# VEGZ Shop — MVP Optimization Plan

## In-scope before GPS and payment gateway
- Validate price and stock updates server-side; reject negative quantities and invalid prices.
- Keep shop ownership checks on every product, inventory and order route.
- Prevent order status skips and prevent cancellation after dispatch.
- Ensure only approved, open shops with available stock are exposed in the customer marketplace.
- Add pagination/search for large product and order lists.
- Record an audit trail for stock/price changes and order status transitions.
- Require unique internal API secrets in production; never use development demo tokens in a deployed environment.

## B2B bulk fulfilment requirements
- Display requested quantity and unit clearly (kg, g, piece, pack, litre).
- Shop can accept, partially fulfil, or reject a bulk quote request with a reason.
- A confirmed quotation snapshots unit price, quantity, taxes/fees and expected delivery window.
- Do not decrement stock for an unconfirmed enquiry; reserve stock only after quote confirmation.
- Keep household orders and bulk quotations distinguishable in the order inbox.

## Acceptance checks
- A shop cannot edit another shop's products.
- Rejected or pending shops do not appear in the public marketplace.
- Negative stock/price and illegal status transitions are rejected.
- Internal order endpoints reject missing/invalid service credentials.
