# Vegz Shop

Shop-owner portal for the Vegz vegetable ordering platform. This is a separate repository from the customer-facing vegz-user app.

## Included in this first version

- Responsive web dashboard for laptop, tablet and mobile.
- Shop-owner development sign-in; owner data is scoped to the signed-in shop.
- Add, edit, hide, remove vegetables and update prices, units, descriptions and image URLs.
- Inventory tracking, including in-stock, low-stock, hidden and out-of-stock states.
- Shop open/closed and accepting-orders controls.
- Orders inbox with status transitions: placed -> accepted -> preparing -> ready -> out for delivery -> delivered. Cancellation is allowed before dispatch.
- Dashboard metrics for catalog, stock, new/active orders and today's sales.
- FastAPI, SQLAlchemy and SQLite by default; MySQL-compatible via DATABASE_URL.
- Dockerfile and GitHub Actions CI.

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
cp backend/.env.example .env
uvicorn backend.app.main:app --reload --port 8000
```

Open the dashboard at http://localhost:8000, API docs at http://localhost:8000/docs, and health check at http://localhost:8000/api/health.

The starter development code is 123456 (or set SHOP_DEMO_CODE). Enter an owner mobile number to create that shop's development account. Never use this login mode in production.

To create sample products, sign in and use POST /api/dev/seed from the API docs. The endpoint seeds only when the shop has no products.

## Environment

Copy backend/.env.example to .env. Set a strong random JWT_SECRET, and configure DATABASE_URL. Default:

```
DATABASE_URL=sqlite:///./vegz_shop.db
```

Example MySQL URL (install pymysql if choosing this driver):

```
DATABASE_URL=mysql+pymysql://vegz_user:YOUR_PASSWORD@127.0.0.1:3306/vegz_shop
```

Container build:

```bash
docker build -t vegz-shop .
docker run --rm -p 8000:8000 -e JWT_SECRET='replace-with-a-long-random-secret' -e APP_ENV=development vegz-shop
```

## API overview

All shop-specific endpoints except health and development login require the Authorization: Bearer <access_token> header.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /api/health | Liveness check |
| POST | /api/auth/demo-login | Development-only owner sign-in |
| GET/PATCH | /api/shop | Read/update shop profile and availability |
| GET/POST | /api/products | List or add catalog items |
| PATCH/DELETE | /api/products/{product_id} | Edit or remove an item |
| GET | /api/orders | Shop orders, optionally filter by status_filter |
| PATCH | /api/orders/{order_id}/status | Advance or cancel an order |
| GET | /api/dashboard | Shop metrics and recent orders |
| POST | /api/dev/seed | Add sample products once per shop |

## Important integration notes

This is a shop-portal foundation and its starter database is separate from the vegz-user repository. The current order API stores shop-side orders independently so the owner dashboard can be developed and tested. Customer orders from vegz-user will not automatically appear here yet. Before real customer launch, both apps must use a shared order/catalog data model (or a secured server-to-server integration) and include a shop identifier per product/order. Do not simply point two independent schemas at the same database without migrations and ownership rules.

Also required before production:

1. Replace development login with verified OTP or an approved identity provider.
2. Add shop onboarding/approval and role-based access controls; secure secrets and configure HTTPS/CORS.
3. Connect live customer order creation and inventory updates, including transaction-safe stock reservation, cancellation/restock policy and idempotency.
4. Add image upload/storage instead of relying only on public image URLs.
5. Add schema migrations, backups, monitoring, rate limiting and end-to-end tests.
6. Confirm legal, payment and customer-data requirements before launch.

## Project structure

```
backend/
  app/main.py        FastAPI API, schema and shop-scoped business logic
  requirements.txt   Python dependencies
frontend/
  index.html         Shop owner app shell
  styles.css         Responsive design
  app.js             API integration and dashboard interactions
Dockerfile
.github/workflows/ci.yml
```
