import json
import os
import re
import secrets
import shutil
import uuid
import httpx
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
PARTNER_ADMIN_TOKEN = os.getenv("PARTNER_ADMIN_TOKEN", "vegz-local-partner-token-change-before-production")
SHOP_INTERNAL_TOKEN = os.getenv("SHOP_INTERNAL_TOKEN", "vegz-local-shop-order-token-change-before-production" if APP_ENV == "development" else "")
ADMIN_SERVICE_URL = os.getenv("ADMIN_SERVICE_URL", "http://host.docker.internal:8000" if APP_ENV == "development" else "").rstrip("/")
if APP_ENV == "production" and (len(PARTNER_ADMIN_TOKEN) < 32 or "replace-with" in PARTNER_ADMIN_TOKEN.lower() or "change-before-production" in PARTNER_ADMIN_TOKEN or not ADMIN_SERVICE_URL):
    raise RuntimeError("Configure ADMIN_SERVICE_URL and a unique PARTNER_ADMIN_TOKEN before production.")
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
    accepts_orders: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


CATALOG = {
    "Tomato": ("Daily essentials", "Juicy, ripe tomatoes for everyday cooking.", "https://images.unsplash.com/photo-1546094096-0df4bcaaa337?auto=format&fit=crop&w=700&q=85", "kg"),
    "Potato": ("Daily essentials", "Fresh everyday potatoes, sorted with care.", "https://images.unsplash.com/photo-1518977676601-b53f82aba655?auto=format&fit=crop&w=700&q=85", "kg"),
    "Red Onion": ("Daily essentials", "Kitchen-ready red onions with a bold flavour.", "https://images.unsplash.com/photo-1508747703725-719777637510?auto=format&fit=crop&w=700&q=85", "kg"),
    "Carrot": ("Fresh picks", "Crunchy carrots, full of colour and freshness.", "https://images.unsplash.com/photo-1445282768818-728615cc910a?auto=format&fit=crop&w=700&q=85", "kg"),
    "Spinach": ("Leafy greens", "Tender green leaves, great for dals and curries.", "https://images.unsplash.com/photo-1576045057995-568f588f82fb?auto=format&fit=crop&w=700&q=85", "bunch"),
    "Broccoli": ("Fresh picks", "Fresh green florets for colourful, healthy meals.", "https://images.unsplash.com/photo-1459411621453-7b03977f4bfc?auto=format&fit=crop&w=700&q=85", "pc"),
    "Cabbage": ("Fresh picks", "Firm, crisp cabbage for salads and stir-fries.", "https://images.unsplash.com/photo-1594282486552-05f4d1e3d3c9?auto=format&fit=crop&w=700&q=85", "pc"),
    "Green Capsicum": ("Fresh picks", "Bright green capsicum with a clean, crisp bite.", "https://images.unsplash.com/photo-1563565375-f3fdfdbefa83?auto=format&fit=crop&w=700&q=85", "kg"),
    "Cucumber": ("Fresh picks", "Crisp cucumbers for salads.", "https://images.unsplash.com/photo-1604977042946-1eecc30f269e?auto=format&fit=crop&w=700&q=85", "kg"),
    "Cauliflower": ("Fresh picks", "Fresh florets for curries.", "https://images.unsplash.com/photo-1568584711075-3d021a7c3ca3?auto=format&fit=crop&w=700&q=85", "pc"),
    "Brinjal": ("Fresh picks", "Glossy brinjals for home cooking.", "https://images.unsplash.com/photo-1659261200848-1f3c2f8a0f19?auto=format&fit=crop&w=700&q=85", "kg"),
    "Lady Finger": ("Fresh picks", "Tender okra for Indian cooking.", "https://images.unsplash.com/photo-1635350673954-9a2f5f2e5e9a?auto=format&fit=crop&w=700&q=85", "kg"),
    "Green Peas": ("Fresh picks", "Sweet peas for curries and snacks.", "https://images.unsplash.com/photo-1604329760661-e71dc83f8f26?auto=format&fit=crop&w=700&q=85", "kg"),
    "Beetroot": ("Fresh picks", "Earthy beetroot for salads and juices.", "https://images.unsplash.com/photo-1607305387299-a3d9611cd469?auto=format&fit=crop&w=700&q=85", "kg"),
    "Radish": ("Fresh picks", "Fresh radish with a peppery crunch.", "https://images.unsplash.com/photo-1598170845058-32b9d6a5da37?auto=format&fit=crop&w=700&q=85", "kg"),
    "Pumpkin": ("Fresh picks", "Sweet pumpkin for comforting meals.", "https://images.unsplash.com/photo-1570586437263-ab629fccc818?auto=format&fit=crop&w=700&q=85", "kg"),
    "Bitter Gourd": ("Fresh picks", "Fresh karela for traditional recipes.", "", "kg"),
    "Bottle Gourd": ("Fresh picks", "Tender bottle gourd for light meals.", "", "pc"),
    "Green Beans": ("Fresh picks", "Crisp beans for stir-fries and sabzi.", "https://images.unsplash.com/photo-1567375698348-5d9d5ae99de0?auto=format&fit=crop&w=700&q=85", "kg"),
    "Sweet Corn": ("Fresh picks", "Sweet corn for snacks and soups.", "https://images.unsplash.com/photo-1551754655-cd27e38d2076?auto=format&fit=crop&w=700&q=85", "pc"),
    "Garlic": ("Daily essentials", "Aromatic garlic for everyday flavour.", "", "kg"),
    "Ginger": ("Daily essentials", "Fresh ginger root for chai and curries.", "https://images.unsplash.com/photo-1615485500704-8e990f9900f2?auto=format&fit=crop&w=700&q=85", "kg"),
    "Green Chilli": ("Daily essentials", "Green chillies to add a little heat.", "https://images.unsplash.com/photo-1563565375-f3fdfdbefa83?auto=format&fit=crop&w=700&q=85", "kg"),
    "Coriander": ("Leafy greens", "Fragrant coriander bunches.", "https://images.unsplash.com/photo-1615485290382-441e4d049cb5?auto=format&fit=crop&w=700&q=85", "bunch"),
    "Mint": ("Leafy greens", "Fresh mint for chutneys and drinks.", "https://images.unsplash.com/photo-1628556270448-4d4e4148e1b1?auto=format&fit=crop&w=700&q=85", "bunch"),
    "Spring Onion": ("Leafy greens", "Spring onions for noodles and stir-fries.", "https://images.unsplash.com/photo-1587049633312-76c8eb07bbc5?auto=format&fit=crop&w=700&q=85", "bunch"),
    "Red Bell Pepper": ("Fresh picks", "Sweet red pepper for colourful meals.", "https://images.unsplash.com/photo-1563565375-f3fdfdbefa83?auto=format&fit=crop&w=700&q=85", "kg"),
    "Lettuce": ("Leafy greens", "Crisp lettuce for salads and wraps.", "https://images.unsplash.com/photo-1556801712-76c8eb07bbc9?auto=format&fit=crop&w=700&q=85", "pc"),
    "Basmati Rice": ("Grocery", "Fragrant rice for biryani and pulao.", "", "kg"),
    "Toor Dal": ("Grocery", "Split pigeon peas for everyday dal.", "", "kg"),
    "Moong Dal": ("Grocery", "Moong dal for khichdi and soups.", "", "kg"),
    "Chana Dal": ("Grocery", "Chana dal for curries and snacks.", "", "kg"),
    "Wheat Flour": ("Grocery", "Everyday atta for soft rotis.", "", "kg"),
    "Besan": ("Grocery", "Gram flour for pakoras and chilla.", "", "kg"),
    "Cooking Oil": ("Grocery", "Kitchen oil for daily meal preparation.", "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=700&q=85", "L"),
    "Sugar": ("Grocery", "Fine sugar for tea and baking.", "https://images.unsplash.com/photo-1581441363689-1f3c3c414635?auto=format&fit=crop&w=700&q=85", "kg"),
    "Salt": ("Grocery", "Essential everyday cooking salt.", "https://images.unsplash.com/photo-1518110925495-5fe2fda0442f?auto=format&fit=crop&w=700&q=85", "kg"),
    "Tea Powder": ("Grocery", "Everyday tea for your morning cup.", "https://images.unsplash.com/photo-1544787219-7f47ccb76574?auto=format&fit=crop&w=700&q=85", "250 g"),
    "Coffee": ("Grocery", "Rich coffee for your daily brew.", "https://images.unsplash.com/photo-1559056199-641a0ac8b55e?auto=format&fit=crop&w=700&q=85", "200 g"),
    "Turmeric Powder": ("Spices", "Golden turmeric powder for cooking.", "https://images.unsplash.com/photo-1615485500704-8e990f9900f2?auto=format&fit=crop&w=700&q=85", "100 g"),
    "Red Chilli Powder": ("Spices", "Ground chilli for warmth and colour.", "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?auto=format&fit=crop&w=700&q=85", "100 g"),
    "Cumin Seeds": ("Spices", "Aromatic cumin for seasoning.", "https://images.unsplash.com/photo-1599909533605-f2c5a5a4c2ca?auto=format&fit=crop&w=700&q=85", "100 g"),
    "Mustard Seeds": ("Spices", "Mustard seeds for tadka and pickles.", "https://images.unsplash.com/photo-1603905179139-2e0a8c1e5f68?auto=format&fit=crop&w=700&q=85", "100 g"),
    "Poha": ("Grocery", "Flattened rice for quick breakfasts.", "https://images.unsplash.com/photo-1604908176997-125f25cc6f3d?auto=format&fit=crop&w=700&q=85", "kg"),
    "Oats": ("Grocery", "Rolled oats for breakfast and baking.", "https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?auto=format&fit=crop&w=700&q=85", "500 g"),
    "Peanuts": ("Grocery", "Crunchy peanuts for snacks and chutneys.", "https://images.unsplash.com/photo-1567892737950-30c4db37cd89?auto=format&fit=crop&w=700&q=85", "kg"),
    "Jaggery": ("Grocery", "Traditional jaggery for sweets and drinks.", "https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=700&q=85", "kg"),
    "Pasta": ("Grocery", "Pantry pasta for quick family meals.", "https://images.unsplash.com/photo-1551462147-ff29053bfc14?auto=format&fit=crop&w=700&q=85", "500 g"),
    "Drumstick": ("Fresh picks", "Tender drumsticks for sambar and saaru.", "", "kg"),
    "Ridge Gourd": ("Fresh picks", "Fresh ridge gourd for palya and dal.", "", "kg"),
    "Snake Gourd": ("Fresh picks", "Mild snake gourd for everyday curries.", "", "kg"),
    "Cluster Beans": ("Fresh picks", "Cluster beans for Karnataka-style palya.", "", "kg"),
    "Ivy Gourd": ("Fresh picks", "Tender tindora for quick stir-fries.", "", "kg"),
    "Raw Banana": ("Fresh picks", "Raw banana for palya and shallow-fried sides.", "", "kg"),
    "Curry Leaves": ("Leafy greens", "Aromatic curry leaves for everyday tempering.", "", "bunch"),
    "Dill Leaves": ("Leafy greens", "Fresh sabsige soppu for palya and akki rotti.", "", "bunch"),
    "Fenugreek Leaves": ("Leafy greens", "Fresh menthya soppu for palya and parathas.", "", "bunch"),
    "Drumstick Leaves": ("Leafy greens", "Fresh nugge soppu for saaru and palya.", "", "bunch"),
    "Coconut": ("Daily essentials", "Fresh coconut for chutney, palya and cooking.", "", "pc"),
    "Lemon": ("Daily essentials", "Juicy lemons for chitranna, drinks and seasoning.", "", "kg"),
    "Ragi Flour": ("Grocery", "Finger millet flour for ragi mudde and ragi rotti.", "", "kg"),
    "Jowar Flour": ("Grocery", "Jowar flour for traditional jolada rotti.", "", "kg"),
    "Rice Flour": ("Grocery", "Rice flour for akki rotti and everyday recipes.", "", "kg"),
    "Rava": ("Grocery", "Semolina for upma, kesari bath and breakfast.", "", "kg"),
    "Urad Dal": ("Grocery", "Urad dal for idli, dosa batter and vada.", "", "kg"),
    "Masoor Dal": ("Grocery", "Masoor dal for quick everyday dal.", "", "kg"),
    "Tamarind": ("Grocery", "Tamarind for saaru, gojju and puliyogare.", "", "250 g"),
    "Dry Coconut": ("Grocery", "Dry coconut for chutney pudi and traditional masala.", "", "pc"),
    "Groundnut Oil": ("Grocery", "Groundnut oil for everyday cooking.", "", "L"),
    "Coconut Oil": ("Grocery", "Coconut oil for cooking and coastal recipes.", "", "L"),
    "Sambar Powder": ("Spices", "Sambar powder for everyday saaru and sambar.", "", "200 g"),
    "Rasam Powder": ("Spices", "Rasam powder for a quick home-style saaru.", "", "100 g"),
    "Chutney Pudi": ("Spices", "Karnataka-style chutney pudi for rotti and idli.", "", "200 g"),
    "Byadgi Chilli": ("Spices", "Byadgi chillies for colour and flavour in masala.", "", "100 g"),
    "Papad": ("Grocery", "Crispy papad for everyday meals.", "", "200 g"),
    "Vermicelli": ("Grocery", "Vermicelli for upma, payasa and quick snacks.", "", "400 g"),
    "Green Gram Whole": ("Grocery", "Whole green gram for usal, sprouts and palya.", "", "kg"),
    "Horse Gram": ("Grocery", "Huruli kaalu for saaru and traditional recipes.", "", "kg"),
}

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
    if "approval_status" not in shop_columns:
        connection.execute(text("ALTER TABLE shops ADD COLUMN approval_status VARCHAR(24) NOT NULL DEFAULT 'pending'"))
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
    reason: str = Field(default="", max_length=300)


class DemoLogin(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    shop_type: str = Field(default="vegetable", pattern=r"^(vegetable|grocery)$")
    city: str = Field(default="Hubli", min_length=2, max_length=100)
    demo_code: str = Field(min_length=4, max_length=10)


def shop_payload(shop: Shop):
    return {"id": shop.id, "owner_phone": shop.owner_phone, "name": shop.name, "shop_type": shop.shop_type, "address": shop.address,
            "city": shop.city, "is_open": shop.is_open, "accepts_orders": shop.accepts_orders, "approval_status": shop.approval_status,
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

def require_approved_shop(shop: Shop = Depends(current_shop)) -> Shop:
    if shop.approval_status != "approved":
        raise HTTPException(status_code=403, detail="Your shop registration is awaiting admin approval.")
    return shop


@app.get("/api/marketplace")
def marketplace(city: str | None = None, db: Session = Depends(get_db)):
    """Public catalog for the requested delivery city; only orderable shops/products are shown."""
    query = select(Shop).where(Shop.approval_status == "approved", Shop.is_open.is_(True), Shop.accepts_orders.is_(True))
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


class AdminApprovalIn(BaseModel):
    phone: str = Field(min_length=8, max_length=24)
    status: str = Field(pattern=r"^(approved|rejected|suspended|pending)$")


@app.post("/api/internal/admin-approval")
def admin_approval(payload: AdminApprovalIn, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    expected = PARTNER_ADMIN_TOKEN
    supplied = authorization.split(" ", 1)[1].strip() if authorization and authorization.lower().startswith("bearer ") else ""
    if len(expected) < 32 or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Partner approval authentication failed.")
    digits = re.sub(r"\D", "", payload.phone)
    phone = "+91" + digits[-10:] if len(digits) >= 10 and (len(digits) == 10 or digits.startswith("91")) else re.sub(r"[^0-9+]", "", payload.phone)
    shop = db.scalar(select(Shop).where(Shop.owner_phone == phone))
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop registration not found.")
    shop.approval_status = payload.status
    if payload.status != "approved":
        shop.is_open = False
        shop.accepts_orders = False
    db.commit()
    db.refresh(shop)
    return shop_payload(shop)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "vegz-shop-api"}


@app.post("/api/auth/demo-login")
def demo_login(payload: DemoLogin, db: Session = Depends(get_db)):
    """Development-only sign-in; replace with SMS OTP/approved identity provider in production."""
    if APP_ENV == "production":
        raise HTTPException(status_code=503, detail="Configure the production identity provider before enabling shop-owner sign-in.")
    digits = re.sub(r"\D", "", payload.phone)
    if len(digits) >= 12 and digits.startswith("91"):
        digits = digits[-10:]
    phone = "+91" + digits if len(digits) == 10 else "+" + digits if len(digits) >= 8 else ""
    if len(digits) < 8:
        raise HTTPException(status_code=400, detail="Enter a valid owner mobile number.")
    if payload.demo_code != os.getenv("SHOP_DEMO_CODE", "123456"):
        raise HTTPException(status_code=400, detail="Invalid development code. Use the configured demo code.")
    normalized_city = " ".join(payload.city.split()).title()
    shop = db.scalar(select(Shop).where(Shop.owner_phone == phone))
    if shop is None:
        duplicate = db.scalar(select(Shop).where(Shop.city == normalized_city, Shop.shop_type == payload.shop_type))
        if duplicate is not None:
            raise HTTPException(status_code=409, detail=f"A {payload.shop_type} shop is already registered in {normalized_city}. Vegz allows only one shop of each type per city.")
        shop = Shop(owner_phone=phone, name="My Vegz Shop", shop_type=payload.shop_type, city=normalized_city, approval_status="pending", is_open=False, accepts_orders=False)
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
    admin_url = ADMIN_SERVICE_URL
    admin_token = PARTNER_ADMIN_TOKEN
    if admin_url and len(admin_token) >= 32:
        try:
            response = httpx.post(admin_url + "/api/internal/partner-requests/shop", headers={"Authorization": "Bearer " + admin_token}, json={
                "name": shop.name, "owner_name": "", "phone": shop.owner_phone, "city": shop.city,
                "shop_type": shop.shop_type, "address": shop.address, "external_ref": str(shop.id)
            }, timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="Could not submit shop registration for admin review. Check the Vegz Admin service and shared partner token.") from exc
    token = jwt.encode({"shop_id": shop.id, "exp": datetime.utcnow() + timedelta(days=7)}, JWT_SECRET, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer", "shop": shop_payload(shop)}


@app.get("/api/shop")
def get_shop(shop: Shop = Depends(current_shop)):
    return shop_payload(shop)


@app.patch("/api/shop")
def update_shop(payload: ShopPatch, shop: Shop = Depends(current_shop), db: Session = Depends(get_db)):
    changes = payload.model_dump(exclude_unset=True)
    if shop.approval_status != "approved" and (changes.get("is_open") is True or changes.get("accepts_orders") is True):
        raise HTTPException(status_code=403, detail="Shop availability can be enabled only after admin approval.")
    if "city" in changes and " ".join(changes["city"].split()).title() != shop.city:
        raise HTTPException(status_code=403, detail="Shop city is fixed at registration. Contact Vegz support if it was entered incorrectly.")
    if "shop_type" in changes and changes["shop_type"] != shop.shop_type:
        raise HTTPException(status_code=403, detail="Shop type is fixed at registration. Contact Vegz support if it was entered incorrectly.")
    target_city = shop.city
    target_type = shop.shop_type
    if "city" in changes or "shop_type" in changes:
        duplicate = db.scalar(select(Shop).where(Shop.id != shop.id, Shop.city == target_city, Shop.shop_type == target_type))
        if duplicate is not None:
            raise HTTPException(status_code=409, detail=f"A {target_type} shop is already registered in {target_city}. Vegz allows only one shop of each type per city.")
    for key, value in changes.items():
        setattr(shop, key, target_city if key == "city" else value)
    db.commit()
    db.refresh(shop)
    return shop_payload(shop)


def catalog_image_for(name: str) -> str:
    """Return the item's own catalog image or a stable category image fallback."""
    values = CATALOG[name]
    if values[2]:
        return values[2]
    category = values[0]
    fallback_names = {
        "Daily essentials": "Tomato",
        "Fresh picks": "Carrot",
        "Leafy greens": "Spinach",
        "Grocery": "Cooking Oil",
        "Spices": "Turmeric Powder",
    }
    fallback = CATALOG.get(fallback_names.get(category, "Tomato"), CATALOG["Tomato"])[2]
    return fallback or CATALOG["Tomato"][2]


@app.get("/api/catalog")
def list_catalog(shop: Shop = Depends(current_shop)):
    return [
        {"name": name, "category": values[0], "description": values[1], "image_url": catalog_image_for(name), "unit": values[3]}
        for name, values in CATALOG.items()
        if (values[0] in {"Grocery", "Spices"}) == (shop.shop_type == "grocery")
    ]


@app.get("/api/products")
def list_products(shop: Shop = Depends(current_shop), db: Session = Depends(get_db)):
    return [product_payload(p) for p in db.scalars(select(Product).where(Product.shop_id == shop.id).order_by(Product.id.desc())).all()]


@app.post("/api/products", status_code=201)
def create_product(payload: ProductIn, shop: Shop = Depends(current_shop), db: Session = Depends(get_db)):
    if payload.name not in CATALOG:
        raise HTTPException(status_code=422, detail="Choose an item from the Vegz catalog.")
    data = payload.model_dump()
    catalog_category, catalog_description, _, catalog_unit = CATALOG[payload.name]
    catalog_image = catalog_image_for(payload.name)
    data["category"], data["description"], data["image_url"], data["unit"] = catalog_category, catalog_description, catalog_image, catalog_unit
    if shop.approval_status != "approved":
        data["is_available"] = False
    data["image_urls"] = json.dumps(([catalog_image] if catalog_image else []) + [u for u in data["image_urls"] if u and u != catalog_image][:2])
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
    changes = payload.model_dump(exclude_unset=True)
    if shop.approval_status != "approved" and changes.get("is_available") is True:
        changes["is_available"] = False
    if "name" in changes and changes["name"] != p.name:
        raise HTTPException(status_code=403, detail="Product identity is fixed by the Vegz catalog.")
    catalog_category, catalog_description, _, catalog_unit = CATALOG[p.name]
    catalog_image = catalog_image_for(p.name)
    changes.pop("name", None)
    changes.pop("category", None)
    changes.pop("description", None)
    changes.pop("unit", None)
    changes.pop("image_url", None)
    for key, value in changes.items():
        if key == "image_urls":
            value = json.dumps((value or [])[:3])
            if value != "[]" and not payload.image_url:
                p.image_url = json.loads(value)[0]
        setattr(p, key, value)
    p.category, p.description, p.unit, p.image_url = catalog_category, catalog_description, catalog_unit, catalog_image
    db.commit()
    db.refresh(p)
    return product_payload(p)


@app.post("/api/products/{product_id}/images")
def upload_product_images(
    product_id: int,
    files: list[UploadFile] = File(...),
    shop: Shop = Depends(require_approved_shop),
    db: Session = Depends(get_db),
):
    if not 1 <= len(files) <= 2:
        raise HTTPException(status_code=400, detail="Upload one or two additional product images.")
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
    base_image = catalog_image_for(product.name) if product.name in CATALOG else product.image_url
    product.image_url = base_image
    product.image_urls = json.dumps(([base_image] if base_image else []) + [url for url in urls if url != base_image][:2])
    db.commit()
    db.refresh(product)
    return product_payload(product)


@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, shop: Shop = Depends(require_approved_shop), db: Session = Depends(get_db)):
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
    expected = SHOP_INTERNAL_TOKEN
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
def list_orders(status_filter: str | None = None, shop: Shop = Depends(require_approved_shop), db: Session = Depends(get_db)):
    query = select(ShopOrder).where(ShopOrder.shop_id == shop.id).order_by(desc(ShopOrder.created_at))
    if status_filter:
        query = query.where(ShopOrder.status == status_filter)
    return [order_payload(o) for o in db.scalars(query).all()]


@app.patch("/api/orders/{order_id}/status")
def update_order_status(order_id: int, payload: OrderStatusPatch, shop: Shop = Depends(require_approved_shop), db: Session = Depends(get_db)):
    allowed = {
        "placed": {"accepted", "rejected", "cancelled"},
        "accepted": {"preparing", "cancelled"},
        "preparing": {"ready", "cancelled"},
        "ready": {"out_for_delivery", "cancelled"},
        "out_for_delivery": {"delivered"},
        "delivered": set(),
        "rejected": set(),
        "cancelled": set(),
    }
    o = db.scalar(select(ShopOrder).where(ShopOrder.id == order_id, ShopOrder.shop_id == shop.id))
    if o is None:
        raise HTTPException(status_code=404, detail="Order not found.")
    next_status = payload.status.strip().lower()
    if next_status not in allowed.get(o.status, set()):
        raise HTTPException(status_code=409, detail=f"Cannot move order from {o.status} to {next_status}.")
    if next_status == "rejected" and not payload.reason.strip():
        raise HTTPException(status_code=422, detail="A rejection reason is required so the customer can be informed.")
    if next_status == "rejected":
        o.note = (o.note + "\n" if o.note else "") + "Rejection reason: " + payload.reason.strip()
    o.status = next_status
    o.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(o)
    return order_payload(o)


@app.get("/api/dashboard")
def dashboard(shop: Shop = Depends(require_approved_shop), db: Session = Depends(get_db)):
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
def seed_demo_data(shop: Shop = Depends(require_approved_shop), db: Session = Depends(get_db)):
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
