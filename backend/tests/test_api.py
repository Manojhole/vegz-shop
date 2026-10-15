import os
import tempfile
import unittest

# Exercise production API routes with an isolated SQLite database and a fixed test token.
DB_FILE = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_FILE.close()
os.environ["DATABASE_URL"] = "sqlite:///" + DB_FILE.name
os.environ["APP_ENV"] = "development"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-test-only"
os.environ["SHOP_DEMO_CODE"] = "123456"
os.environ["PARTNER_ADMIN_TOKEN"] = "test-partner-admin-token-that-is-long-enough"
os.environ["ADMIN_SERVICE_URL"] = ""

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


class ShopApiTests(unittest.TestCase):
    def setUp(self):
        phone = "+919876543210"
        response = client.post("/api/auth/demo-login", json={"phone": phone, "demo_code": "123456"})
        self.assertEqual(response.status_code, 200, response.text)
        self.headers = {"Authorization": "Bearer " + response.json()["access_token"]}
        approved = client.post("/api/internal/admin-approval", headers={"Authorization": "Bearer test-partner-admin-token-that-is-long-enough"}, json={"phone": phone, "status": "approved"})
        self.assertEqual(approved.status_code, 200, approved.text)

    def test_shop_scoped_product_lifecycle(self):
        before = client.get("/api/products", headers=self.headers)
        self.assertEqual(before.status_code, 200)
        response = client.post("/api/products", headers=self.headers, json={
            "name": "Tomato", "category": "Fresh picks", "unit": "kg",
            "price": 39.5, "stock_qty": 12, "is_available": True,
        })
        self.assertEqual(response.status_code, 201, response.text)
        product = response.json()
        self.assertEqual(product["stock_qty"], 12)
        changed = client.patch(f"/api/products/{product['id']}", headers=self.headers, json={"stock_qty": 0})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["stock_state"], "out_of_stock")
        deleted = client.delete(f"/api/products/{product['id']}", headers=self.headers)
        self.assertEqual(deleted.status_code, 200)

    def test_shop_type_and_city_are_registration_only(self):
        city_change = client.patch("/api/shop", headers=self.headers, json={"city": "Dharwad"})
        self.assertEqual(city_change.status_code, 403)
        type_change = client.patch("/api/shop", headers=self.headers, json={"shop_type": "grocery"})
        self.assertEqual(type_change.status_code, 403)

    def test_shop_availability_settings(self):
        response = client.patch("/api/shop", headers=self.headers, json={"is_open": False, "accepts_orders": False})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_open"])
        self.assertFalse(response.json()["accepts_orders"])

    def test_registration_requires_admin_approval_and_catalog_is_predefined(self):
        response = client.post("/api/auth/demo-login", json={"phone": "+919876543211", "demo_code": "123456", "shop_type": "vegetable", "city": "Dharwad"})
        self.assertEqual(response.status_code, 200, response.text)
        token = {"Authorization": "Bearer " + response.json()["access_token"]}
        self.assertEqual(response.json()["shop"]["approval_status"], "pending")
        self.assertEqual(client.get("/api/products", headers=token).status_code, 403)
        catalog = client.get("/api/catalog", headers=token)
        self.assertEqual(catalog.status_code, 200)
        self.assertTrue(any(item["image_url"] for item in catalog.json()))
        approved = client.post("/api/internal/admin-approval", headers={"Authorization": "Bearer test-partner-admin-token-that-is-long-enough"}, json={"phone": "+919876543211", "status": "approved"})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(client.get("/api/products", headers=token).status_code, 200)

    def test_auth_required(self):
        response = client.get("/api/products")
        self.assertEqual(response.status_code, 401)


    def test_customer_marketplace_only_exposes_approved_open_orderable_stock(self):
        product = client.post("/api/products", headers=self.headers, json={
            "name": "Tomato", "price": 34, "stock_qty": 8, "is_available": True,
            "image_urls": ["https://example.test/shop-tomato-1.jpg", "https://example.test/shop-tomato-2.jpg"]
        })
        self.assertEqual(product.status_code, 201, product.text)
        payload = product.json()
        self.assertTrue(payload["image_urls"][0])
        self.assertEqual(len(payload["image_urls"]), 3)
        self.assertNotEqual(payload["image_urls"][0], "https://example.test/shop-tomato-1.jpg")
        enabled = client.patch("/api/shop", headers=self.headers, json={"is_open": True, "accepts_orders": True})
        self.assertEqual(enabled.status_code, 200, enabled.text)
        visible = client.get("/api/marketplace?city=Hubli")
        self.assertEqual(visible.status_code, 200, visible.text)
        matching = [shop for shop in visible.json() if shop["shop_id"] == enabled.json()["id"]]
        self.assertEqual(len(matching), 1)
        self.assertTrue(any(item["name"] == "Tomato" for item in matching[0]["products"]))
        hidden_city = client.get("/api/marketplace?city=Dharwad")
        self.assertEqual(hidden_city.status_code, 200)
        self.assertFalse(any(shop["shop_id"] == enabled.json()["id"] for shop in hidden_city.json()))

    def test_registration_is_sent_to_admin_review_queue(self):
        from unittest.mock import Mock, patch
        with patch("backend.app.main.ADMIN_SERVICE_URL", "http://admin.test"), patch("backend.app.main.httpx.post", return_value=Mock(raise_for_status=Mock())) as callback:
            response = client.post("/api/auth/demo-login", json={
                "phone": "9876543212", "demo_code": "123456", "shop_type": "grocery", "city": "Hubli"
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["shop"]["approval_status"], "pending")
        args, kwargs = callback.call_args
        self.assertEqual(args[0], "http://admin.test/api/internal/partner-requests/shop")
        self.assertEqual(kwargs["json"]["phone"], "+919876543212")
        self.assertEqual(kwargs["json"]["shop_type"], "grocery")
        self.assertEqual(kwargs["json"]["city"], "Hubli")

if __name__ == "__main__":
    unittest.main()
