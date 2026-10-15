import json
import os
import re
import secrets
import shutil
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, create_engine, select, desc
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy import inspect, text

load_dotenv()
APP_ENV = os.getenv("APP_ENV", "development").lower()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vegz_shop.db")
JWT_SECRET = os.getenv("JWT_SECRET", "local-dev-only-change-this-secret")
engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Shop(Base):
    __tablename__ = "shops"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="My Vegz Shop")
    shop_type: Mapped[str] = mapped_column(String(20), default="vegetable", index=True)
    address: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str] = mapped_column(String(100), default="Hubli", index=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    accepts_orders: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(60), default="Vegetables")
    description: Mapped[str] = mapped_column(String(300), default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    image_urls: Mapped[str] = mapped_column(Text, default="[]")
    unit: Mapped[str] = mapped_column(String(24), default="kg")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ShopOrder(Base):
    __tablename__ = "shop_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)
    customer_name: Mapped[str] = mapped_column(String(120), default="Vegz customer")
    customer_phone: Mapped[str] = mapped_column(String(20), default="")
    delivery_address: Mapped[str] = mapped_column(String(400), default="")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    status: Mapped[str] = mapped_column(String(32), default="placed", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Base.metadata.create_all(bind=engine)
# Additive migration for existing SQLite/MySQL installations.
with engine.begin() as connection:
    columns = {column["name"] for column in inspect(engine).get_columns("products")}
    if "image_urls" not in columns:
        connection.execute(text("ALTER TABLE products ADD COLUMN image_urls TEXT NOT NULL DEFAULT '[]'"))
    shop_columns = {column["name"] for column in inspect(engine).get_columns("shops")}
    if "shop_type" not in shop_columns:
        connection.execute(text("ALTER TABLE shops ADD COLUMN shop_type VARCHAR(20) NOT NULL DEFAULT 'vegetable'"))
    if "city" not in shop_columns:
        connection.execute(text("ALTER TABLE shops ADD COLUMN city VARCHAR(100) NOT NULL DEFAULT 'Hubli'"))
    duplicate_city_types = connection.execute(text(
        "SELECT city, shop_type FROM shops GROUP BY city, shop_type HAVING COUNT(*) > 1"
    )).fetchall()
    if not duplicate_city_types:
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_shops_city_type ON shops (city, shop_type)"
        ))

app = FastAPI(title="Vegz Shop API", version="1.0.1", description="Shop-owner catalog, inventory, availability, and order operations.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if x.strip()],
    allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(default="Vegetables", max_length=60)
    description: str = Field(default="", max_length=300)
    image_url: str = Field(default="", max_length=500)
    image_urls: list[str] = Field(default_factory=list, max_length=3)
    unit: str = Field(default="kg", max_length=24)
    price: Decimal = Field(gt=0, le=100000)
    stock_qty: int = Field(default=0, ge=0, le=1000000)
    is_available: bool = True


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=300)
    image_url: str | None = Field(default=None, max_length=500)
    image_urls: list[str] | None = Field(default=None, max_length=3)
    unit: str | None = Field(default=None, max_length=24)
    price: Decimal | None = Field(default=None, gt=0, le=100000)
    stock_qty: int | None = Field(default=None, ge=0, le=1000000)
    is_available: bool | None = None


class ShopPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    shop_type: str | None = Field(default=None, pattern=r"^(vegetable|grocery)$")
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    is_open: bool | None = None
    accepts_orders: bool | None = None


class InternalOrderItem(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=99)


class InternalShopOrder(BaseModel):
    shop_id: int
    customer_name: str = Field(min_length=2, max_length=120)
    customer_phone: str = Field(default="", max_length=20)
    delivery_address: str = Field(min_length=4, max_length=400)
    items: list[InternalOrderItem] = Field(min_length=1, max_length=60)
    order_reference: str = Field(min_length=4, max_length=80)


class OrderStatusPatch(BaseModel):
    status: str


class DemoLogin(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    shop_type: str = Field(default="vegetable", pattern=r"^(vegetable|grocery)$")
    city: str = Field(default="Hubli", min_length=2, max_length=100)
    demo_code: str = Field(min_length=4, max_length=10)


def shop_payload(shop: Shop):
    return {"id": shop.id, "owner_phone": shop.owner_phone, "name": shop.name, "shop_type": shop.shop_type, "address": shop.address,
            "city": shop.city, "is_open": shop.is_open, "accepts_orders": shop.accepts_orders,
            "created_at": shop.created_at.isoformat() + "Z"}


def product_payload(p: Product):
    try:
        images = json.loads(p.image_urls or "[]")
    except (TypeError, ValueError):
        images = []
    if not images and p.image_url:
        images = [p.image_url]
    return {"id": p.id, "shop_id": p.shop_id, "name": p.name, "category": p.category, "description": p.description,
            "image_url": p.image_url, "image_urls": images[:3], "unit": p.unit, "price": float(p.price),
            "stock_qty": p.stock_qty, "stock_state": "out_of_stock" if p.stock_qty <= 0 else "in_stock",
            "is_available": bool(p.is_available),
            "customer_can_order": bool(p.is_available and p.stock_qty > 0),
            "created_at": p.created_at.isoformat() + "Z"}


def order_payload(o: ShopOrder):
    return {"id": o.id, "customer_name": o.customer_name, "customer_phone": o.customer_phone,
            "delivery_address": o.delivery_address, "total_amount": float(o.total_amount),
            "status": o.status, "note": o.note,
            "created_at": o.created_at.isoformat() + "Z", "updated_at": o.updated_at.isoformat() + "Z"}


def current_shop(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Shop:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in as the shop owner first.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        shop_id = int(payload["shop_id"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    shop = db.get(Shop, shop_id)
    if shop is None:
        raise HTTPException(status_code=401, detail="Shop account not found.")
    return shop


@app.get("/api/marketplace")
def marketplace(city: str | None = None, db: Session = Depends(get_db)):
    """Public catalog for the requested delivery city; only orderable shops/products are shown."""
    query = select(Shop).where(Shop.is_open.is_(True), Shop.accepts_orders.is_(True))
    if city and city.strip():
        query = query.where(Shop.city == city.strip().title())
    shops = db.scalars(query.order_by(Shop.id)).all()
    result = []
    seen_city_types: set[tuple[str, str]] = set()
    for shop in shops:
        # Protect the customer catalog from legacy duplicate accounts while keeping old data intact.
        city_type = (shop.city.strip().casefold(), shop.shop_type)
        if city_type in seen_city_types:
            continue
        items = db.scalars(select(Product).where(
            Product.shop_id == shop.id, Product.is_available.is_(True), Product.stock_qty > 0
        ).order_by(Product.category, Product.name)).all()
        if not items:
            continue
        seen_city_types.add(city_type)
        result.append({
            "shop_id": shop.id, "shop_name": shop.name, "shop_type": shop.shop_type, "shop_address": shop.address,
            "products": [product_payload(item) for item in items],
        })
    return result


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "vegz-shop-api"}


@app.post("/api/auth/demo-login")
def demo_login(payload: DemoLogin, db: Session = Depends(get_db)):
    """Development-only sign-in; replace with SMS OTP/approved identity provider in production."""
    if APP_ENV == "production":
        raise HTTPException(status_code=503, detail="Configure the production identity provider before enabling shop-owner sign-in.")
    phone = re.sub(r"[^0-9+]", "", payload.phone)
    if len(re.sub(r"\D", "", phone)) < 8:
        raise HTTPException(status_code=400, detail="Enter a valid owner mobile number.")
    if payload.demo_code != os.getenv("SHOP_DEMO_CODE", "123456"):
        raise HTTPException(status_code=400, detail="Invalid development code. Use the configured demo code.")
    normalized_city = " ".join(payload.city.split()).title()
    shop = db.scalar(select(Shop).where(Shop.owner_phone == phone))
    if shop is None:
        duplicate = db.scalar(select(Shop).where(Shop.city == normalized_city, Shop.shop_type == payload.shop_type))
        if duplicate is not None:
            raise HTTPException(status_code=409, detail=f"A {payload.shop_type} shop is already registered in {normalized_city}. Vegz allows only one shop of each type per city.")
        shop = Shop(owner_phone=phone, name="My Vegz Shop", shop_type=payload.shop_type, city=normalized_city)
        db.add(shop)
        db.commit()
        db.refresh(shop)
    else:
        if not shop.city:
            duplicate = db.scalar(select(Shop).where(Shop.id != shop.id, Shop.city == normalized_city, Shop.shop_type == shop.shop_type))
            if duplicate is not None:
                raise HTTPException(status_code=409, detail=f"A {shop.shop_type} shop is already registered in {normalized_city}.")
            shop.city = normalized_city
            db.commit()
            db.refresh(shop)
    token = jwt.encode({"shop_id": shop.id, "exp": datetime.utcnow() + timedelta(days=7)}, JWT_SECRET, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer", "shop": shop_payload(shop)}


@app.get("/api/shop")
def get_shop(shop: Shop = Depends(current_shop)):
    return shop_payload(shop)


@app.patch("/api/shop")
def update_shop(payload: ShopPatch, shop: Shop = Depends(current_shop), db: Session = Depends(get_db)):
    changes = payload.model_dump(exclude_unset=True)
    target_city = " ".join((changes.get("city") or shop.city).split()).title()
    target_type = changes.get("shop_type") or shop.shop_type
    if "city" in changes or "shop_type" in changes:
        duplicate = db.scalar(select(Shop).where(Shop.id != shop.id, Shop.city == target_city, Shop.shop_type == target_type))
        if duplicate is not None:
            raise HTTPException(status_code=409, detail=f"A {target_type} shop is already registered in {target_city}. Vegz allows only one shop of each type per city.")
    for key, value in changes.items():
        setattr(shop, key, target_city if key == "city" else value)
    db.commit()
    db.refresh(shop)
    return shop_payload(shop)


@app.get("/api/products")
def list_products(shop: Shop = Depends(current_shop), db: Session = Depends(get_db)):
    return [product_payload(p) for p in db.scalars(select(Product).where(Product.shop_id == shop.id).order_by(Product.id.desc())).all()]


@app.post("/api/products", status_code=201)
def create_product(payload: ProductIn, shop: Shop = Depends(current_shop), db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["image_urls"] = json.dumps(data["image_urls"][:3])
    if not data["image_url"] and data["image_urls"]:
        data["image_url"] = data["image_urls"][0]
    p = Product(shop_id=shop.id, **data)
    db.add(p)
    db.commit()
    db.refresh(p)
    return product_payload(p)


@app.patch("/api/products/{product_id}")
def update_product(product_id: int, payload: ProductPatch, shop: Shop = Depends(current_shop), db: Session = Depends(get_db)):
    p = db.scalar(select(Product).where(Product.id == product_id, Product.shop_id == shop.id))
    if p is None:
        raise HTTPException(status_code=404, detail="Vegetable not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "image_urls":
            value = json.dumps((value or [])[:3])
            if value != "[]" and not payload.image_url:
                p.image_url = json.loads(value)[0]
        setattr(p, key, value)
    db.commit()
    db.refresh(p)
    return product_payload(p)


@app.post("/api/products/{product_id}/images")
def upload_product_images(
    product_id: int,
    files: list[UploadFile] = File(...),
    shop: Shop = Depends(current_shop),
    db: Session = Depends(get_db),
):
    if not 1 <= len(files) <= 3:
        raise HTTPException(status_code=400, detail="Upload between 1 and 3 product images.")
    product = db.scalar(select(Product).where(Product.id == product_id, Product.shop_id == shop.id))
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    upload_dir = Path(__file__).resolve().parents[2] / "frontend" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    urls = []
    for upload in files:
        suffix = allowed.get(upload.content_type or "")
        if not suffix:
            raise HTTPException(status_code=415, detail="Use JPG, PNG or WEBP images.")
        data = upload.file.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Each image must be 5 MB or smaller.")
        filename = f"{uuid.uuid4().hex}{suffix}"
        with (upload_dir / filename).open("wb") as image_file:
            image_file.write(data)
        urls.append(f"/uploads/{filename}")
    product.image_urls = json.dumps(urls)
    product.image_url = urls[0]
    db.commit()
    db.refresh(product)
    return product_payload(product)


@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, shop: Shop = Depends(current_shop), db: Session = Depends(get_db)):
    p = db.scalar(select(Product).where(Product.id == product_id, Product.shop_id == shop.id))
    if p is None:
        raise HTTPException(status_code=404, detail="Vegetable not found.")
    db.delete(p)
    db.commit()
    return {"message": "Vegetable removed from your catalog."}


@app.post("/api/internal/orders", status_code=201)
def create_internal_order(
    payload: InternalShopOrder,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Create a shop-owned suborder from the trusted customer-order service."""
    expected = os.getenv("SHOP_INTERNAL_TOKEN", "")
    supplied = authorization.split(" ", 1)[1].strip() if authorization and authorization.lower().startswith("bearer ") else ""
    if len(expected) < 32 or "replace-with" in expected.lower() or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Internal order authentication failed.")
    shop = db.get(Shop, payload.shop_id)
    if shop is None or not shop.is_open or not shop.accepts_orders:
        raise HTTPException(status_code=409, detail="This shop is not accepting orders.")
    existing_order = db.scalar(select(ShopOrder).where(
        ShopOrder.shop_id == shop.id, ShopOrder.note.like("%Reference: " + payload.order_reference + " |%")
    ))
    if existing_order is not None:
        return {**order_payload(existing_order), "shop_id": shop.id, "shop_name": shop.name,
                "shop_phone": shop.owner_phone, "shop_address": shop.address,
                "order_reference": payload.order_reference}

    quantities: dict[int, int] = {}
    for item in payload.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    products = {}
    for product_id, quantity in quantities.items():
        product = db.scalar(select(Product).where(
            Product.id == product_id, Product.shop_id == shop.id,
            Product.is_available.is_(True), Product.stock_qty >= quantity,
        ).with_for_update())
        if product is None:
            raise HTTPException(status_code=409, detail="An item is unavailable or has insufficient stock.")
        products[product_id] = product
    total = Decimal("0.00")
    summaries = []
    for product_id, quantity in quantities.items():
        product = products[product_id]
        total += Decimal(str(product.price)) * quantity
        summaries.append(f"{product.name} x{quantity}")
    total = total.quantize(Decimal("0.01"))
    order = ShopOrder(
        shop_id=shop.id, customer_name=payload.customer_name,
        customer_phone=payload.customer_phone, delivery_address=payload.delivery_address,
        total_amount=total, status="placed",
        note="Reference: " + payload.order_reference + " | Items: " + ", ".join(summaries),
    )
    for product_id, quantity in quantities.items():
        products[product_id].stock_qty -= quantity
    db.add(order)
    db.commit()
    db.refresh(order)
    return {**order_payload(order), "shop_id": shop.id, "shop_name": shop.name, "shop_phone": shop.owner_phone, "shop_address": shop.address,
            "items": summaries, "order_reference": payload.order_reference}


@app.get("/api/orders")
def list_orders(status_filter: str | None = None, shop: Shop = Depends(current_shop), db: Session = Depends(get_db)):
    query = select(ShopOrder).where(ShopOrder.shop_id == shop.id).order_by(desc(ShopOrder.created_at))
    if status_filter:
        query = query.where(ShopOrder.status == status_filter)
    return [order_payload(o) for o in db.scalars(query).all()]


@app.patch("/api/orders/{order_id}/status")
def update_order_status(order_id: int, payload: OrderStatusPatch, shop: Shop = Depends(current_shop), db: Session = Depends(get_db)):
    allowed = {
        "placed": {"accepted", "cancelled"},
        "accepted": {"preparing", "cancelled"},
        "preparing": {"ready", "cancelled"},
        "ready": {"out_for_delivery", "cancelled"},
        "out_for_delivery": {"delivered"},
        "delivered": set(),
        "cancelled": set(),
    }
    o = db.scalar(select(ShopOrder).where(ShopOrder.id == order_id, ShopOrder.shop_id == shop.id))
    if o is None:
        raise HTTPException(status_code=404, detail="Order not found.")
    next_status = payload.status.strip().lower()
    if next_status not in allowed.get(o.status, set()):
        raise HTTPException(status_code=409, detail=f"Cannot move order from {o.status} to {next_status}.")
    o.status = next_status
    o.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(o)
    return order_payload(o)


@app.get("/api/dashboard")
def dashboard(shop: Shop = Depends(current_shop), db: Session = Depends(get_db)):
    products = db.scalars(select(Product).where(Product.shop_id == shop.id)).all()
    orders = db.scalars(select(ShopOrder).where(ShopOrder.shop_id == shop.id).order_by(desc(ShopOrder.created_at))).all()
    today = datetime.utcnow().date()
    todays = [o for o in orders if o.created_at.date() == today and o.status != "cancelled"]
    return {"shop": shop_payload(shop), "metrics": {
        "products": len(products),
        "in_stock": sum(1 for p in products if p.stock_qty > 0 and p.is_available),
        "out_of_stock": sum(1 for p in products if p.stock_qty <= 0 or not p.is_available),
        "new_orders": sum(1 for o in orders if o.status == "placed"),
        "active_orders": sum(1 for o in orders if o.status in {"accepted", "preparing", "ready", "out_for_delivery"}),
        "today_sales": round(sum(float(o.total_amount) for o in todays if o.status != "cancelled"), 2),
    }, "recent_orders": [order_payload(o) for o in orders[:5]]}


@app.post("/api/dev/seed")
def seed_demo_data(shop: Shop = Depends(current_shop), db: Session = Depends(get_db)):
    """Creates sample vegetable listings once for this shop."""
    if db.scalar(select(Product.id).where(Product.shop_id == shop.id).limit(1)) is not None:
        return {"message": "This shop already has products."}
    items = [
        ("Tomato", "Daily essentials", "kg", "32.00", 40),
        ("Potato", "Daily essentials", "kg", "28.00", 55),
        ("Onion", "Daily essentials", "kg", "36.00", 30),
        ("Carrot", "Fresh picks", "kg", "45.00", 18),
        ("Spinach", "Leafy greens", "bunch", "20.00", 12),
    ]
    for name, category, unit, price, stock in items:
        db.add(Product(shop_id=shop.id, name=name, category=category, unit=unit, price=Decimal(price), stock_qty=stock))
    db.commit()
    return {"message": "Sample vegetables added."}


frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
