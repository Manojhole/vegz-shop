# Vegz Shop

Shop-owner portal and mobile app for vegetable and grocery shops that supply Vegz orders.

## Stack

- Web portal: Next.js + TypeScript under `web/`
- Android/iOS client: React Native + Expo Router under `mobile/`
- API and business logic: FastAPI + SQLAlchemy under `backend/`
- Database: SQLite by default, PostgreSQL/MySQL URLs supported by SQLAlchemy.

## Available workflows

- Development phone/code login; shop city/type are saved at registration.
- Shop registration remains pending until admin approval. Pending shops cannot publish sellable products or accept orders.
- Choose items from the predefined Vegz catalog; catalog photos are included. Set price and opening stock.
- New product listings enter `pending` moderation and stay out of the customer marketplace until an administrator approves them. Moderation status is synchronized to the admin service; existing listings are preserved as approved by the additive migration.
- Edit stock and availability; switch an approved shop open/closed.
- View shop orders and advance allowed order states.
- Upload images from the legacy web dashboard; the mobile app can upload one or two additional JPG/PNG/WEBP photos (5 MB max each) using Expo’s photo picker.
- Authenticated `/api/internal/orders` accepts shop-owned suborders from the customer service.

Development access code defaults to `123456`. Do not use development login for a public/production release.

## Run the web portal

```bash
cd web
npm install
NEXT_PUBLIC_VEGZ_SHOP_API_URL=http://localhost:8002 npm run dev
```

Open `http://localhost:3000`. The Next.js portal now calls the FastAPI service directly for shop login, catalog listing, product/stock changes, shop availability and order status. Open the API-served legacy dashboard on port 8002 for the remaining image-gallery upload workflow.

## Run the Expo app

```bash
cd mobile
npm install
npm run android
```

Android emulator API default: `http://10.0.2.2:8002`. Override with `EXPO_PUBLIC_VEGZ_SHOP_API_URL` for a physical device / LAN development address.

## Shared local stack

`../vegz-admin/docker-compose.postgres.yml` defines PostgreSQL plus the four APIs and web clients. From the admin repository directory:

```bash
docker-compose -f docker-compose.postgres.yml up --build -d
```

Keep existing volumes. Do not use `down -v`.

## CI

The `dev` workflow runs Python syntax, API unit tests, legacy JavaScript syntax validation, Next.js web build, and Expo TypeScript checking.

## Required before launch

- Production identity provider / verified OTP and rate limits.
- Stock reservation and rollback under concurrent orders.
- Object-storage-backed image uploads with access controls.
- Schema migrations, backups, observability, and end-to-end test of order/dispatch lifecycle.
