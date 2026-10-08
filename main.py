
import os
import json
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    Boolean, DateTime, ForeignKey, Text, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from dotenv import load_dotenv


# ============================================================
# 1. DATABASE CONFIGURATION
# ============================================================

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost:3306/food_delivery_db"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)

Base = declarative_base()


# ============================================================
# 2. DATABASE MODELS
# ============================================================

class Restaurant(Base):
    __tablename__ = "restaurants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    address = Column(String(255), nullable=False)
    phone = Column(String(20))
    cuisine = Column(String(100))
    is_open = Column(Boolean, default=True)

    menu_items = relationship(
        "MenuItem",
        back_populates="restaurant"
    )


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(
        Integer,
        ForeignKey("restaurants.id"),
        nullable=False
    )

    name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    available = Column(Boolean, default=True)

    restaurant = relationship(
        "Restaurant",
        back_populates="menu_items"
    )


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    phone = Column(String(20))


class DeliveryPartner(Base):
    __tablename__ = "delivery_partners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    available = Column(Boolean, default=True)


class Cart(Base):
    __tablename__ = "carts"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id"),
        nullable=False
    )
    restaurant_id = Column(
        Integer,
        ForeignKey("restaurants.id"),
        nullable=False
    )


class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(
        Integer,
        ForeignKey("carts.id"),
        nullable=False
    )
    menu_item_id = Column(
        Integer,
        ForeignKey("menu_items.id"),
        nullable=False
    )
    quantity = Column(Integer, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)

    customer_id = Column(
        Integer,
        ForeignKey("customers.id"),
        nullable=False
    )

    restaurant_id = Column(
        Integer,
        ForeignKey("restaurants.id"),
        nullable=False
    )

    delivery_partner_id = Column(
        Integer,
        ForeignKey("delivery_partners.id"),
        nullable=True
    )

    total_amount = Column(Float, nullable=False)
    delivery_address = Column(String(255), nullable=False)

    status = Column(String(50), default="PLACED")
    payment_status = Column(String(50), default="PENDING")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.id"),
        nullable=False
    )

    menu_item_id = Column(
        Integer,
        ForeignKey("menu_items.id"),
        nullable=False
    )

    item_name = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)

    order = relationship(
        "Order",
        back_populates="items"
    )


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.id"),
        nullable=False
    )

    amount = Column(Float, nullable=False)
    method = Column(String(50))
    status = Column(String(50), default="PENDING")
    transaction_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(
        Integer,
        ForeignKey("restaurants.id"),
        nullable=False
    )

    customer_id = Column(
        Integer,
        ForeignKey("customers.id"),
        nullable=False
    )

    rating = Column(Integer, nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


# ============================================================
# 3. FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Food Ordering and Delivery Application",
    description="Complete Food Delivery Platform using FastAPI and MySQL",
    version="1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
# 4. PYDANTIC REQUEST MODELS
# ============================================================

class RestaurantCreate(BaseModel):
    name: str
    address: str
    phone: str
    cuisine: str


class MenuCreate(BaseModel):
    name: str
    description: str = ""
    price: float = Field(gt=0)
    available: bool = True


class CustomerCreate(BaseModel):
    name: str
    email: str
    phone: str


class PartnerCreate(BaseModel):
    name: str
    phone: str


class CartItemInput(BaseModel):
    menu_item_id: int
    quantity: int = Field(gt=0)


class CheckoutRequest(BaseModel):
    customer_id: int
    delivery_address: str


class PaymentRequest(BaseModel):
    order_id: int
    method: str


class ReviewCreate(BaseModel):
    customer_id: int
    restaurant_id: int
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class StatusUpdate(BaseModel):
    status: str


# ============================================================
# 5. WEBSOCKET CONNECTION MANAGER
# ============================================================

class ConnectionManager:

    def __init__(self):
        self.connections = {}

    async def connect(self, order_id, websocket):
        await websocket.accept()

        if order_id not in self.connections:
            self.connections[order_id] = []

        self.connections[order_id].append(websocket)

    def disconnect(self, order_id, websocket):
        if order_id in self.connections:
            if websocket in self.connections[order_id]:
                self.connections[order_id].remove(websocket)

    async def broadcast(self, order_id, message):
        clients = self.connections.get(order_id, [])

        for client in clients.copy():
            try:
                await client.send_json(message)
            except Exception:
                self.disconnect(order_id, client)


manager = ConnectionManager()


# ============================================================
# 6. HELPER FUNCTIONS
# ============================================================

VALID_STATUSES = [
    "PLACED",
    "CONFIRMED",
    "PREPARING",
    "READY_FOR_PICKUP",
    "PICKED_UP",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "CANCELLED"
]


def get_order_dict(order):
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "restaurant_id": order.restaurant_id,
        "delivery_partner_id": order.delivery_partner_id,
        "total_amount": order.total_amount,
        "delivery_address": order.delivery_address,
        "status": order.status,
        "payment_status": order.payment_status,
        "created_at": order.created_at.isoformat(),
        "items": [
            {
                "menu_item_id": item.menu_item_id,
                "name": item.item_name,
                "quantity": item.quantity,
                "price": item.price
            }
            for item in order.items
        ]
    }


def get_cart_dict(cart, db):
    items = db.query(CartItem).filter(
        CartItem.cart_id == cart.id
    ).all()

    result = []
    total = 0

    for cart_item in items:
        menu = db.query(MenuItem).filter(
            MenuItem.id == cart_item.menu_item_id
        ).first()

        if menu:
            subtotal = menu.price * cart_item.quantity
            total += subtotal

            result.append({
                "menu_item_id": menu.id,
                "name": menu.name,
                "price": menu.price,
                "quantity": cart_item.quantity,
                "subtotal": round(subtotal, 2)
            })

    return {
        "cart_id": cart.id,
        "customer_id": cart.customer_id,
        "restaurant_id": cart.restaurant_id,
        "items": result,
        "total": round(total, 2)
    }


# ============================================================
# 7. HOME PAGE / BASIC CUSTOMER INTERFACE
# ============================================================

@app.get("/", response_class=HTMLResponse)
def home():

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Food Delivery App</title>

        <style>
            body {
                font-family: Arial, sans-serif;
                background: #f5f5f5;
                margin: 0;
                color: #333;
            }

            header {
                background: #e85d04;
                color: white;
                padding: 22px;
                text-align: center;
            }

            main {
                max-width: 950px;
                margin: 25px auto;
                padding: 20px;
            }

            .card {
                background: white;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 2px 8px #ddd;
            }

            input, button {
                padding: 10px;
                margin: 5px;
                border-radius: 5px;
                border: 1px solid #ccc;
            }

            button {
                background: #e85d04;
                color: white;
                border: none;
                cursor: pointer;
            }

            button:hover {
                background: #c94d00;
            }

            .restaurant {
                border-bottom: 1px solid #ddd;
                padding: 12px;
            }

            #output {
                white-space: pre-wrap;
                background: #222;
                color: #8fff8f;
                padding: 15px;
                border-radius: 6px;
                overflow-wrap: anywhere;
            }
        </style>
    </head>

    <body>

    <header>
        <h1>Food Ordering & Delivery</h1>
        <p>Order food, track delivery, and enjoy!</p>
    </header>

    <main>

        <div class="card">
            <h2>Customer Registration</h2>

            <input id="customerName" placeholder="Your name">
            <input id="customerEmail" placeholder="Email">
            <input id="customerPhone" placeholder="Phone">

            <button onclick="registerCustomer()">
                Register
            </button>
        </div>

        <div class="card">
            <h2>Restaurants</h2>

            <button onclick="loadRestaurants()">
                View Restaurants
            </button>

            <div id="restaurants"></div>
        </div>

        <div class="card">
            <h2>Shopping Cart</h2>

            <input id="customerId" type="number"
                   placeholder="Customer ID">

            <input id="restaurantId" type="number"
                   placeholder="Restaurant ID">

            <input id="menuId" type="number"
                   placeholder="Menu Item ID">

            <input id="quantity" type="number"
                   placeholder="Quantity" value="1">

            <button onclick="addToCart()">
                Add to Cart
            </button>

            <button onclick="viewCart()">
                View Cart
            </button>

            <div id="cart"></div>
        </div>

        <div class="card">
            <h2>Checkout</h2>

            <input id="deliveryAddress"
                   placeholder="Delivery address">

            <button onclick="checkout()">
                Place Order
            </button>

            <div id="orderResult"></div>
        </div>

        <div class="card">
            <h2>Track Order</h2>

            <input id="trackOrderId"
                   type="number"
                   placeholder="Order ID">

            <button onclick="trackOrder()">
                Track Order
            </button>

            <button onclick="connectTracking()">
                Enable Live Tracking
            </button>

            <div id="tracking"></div>
        </div>

        <div class="card">
            <h2>API Documentation</h2>
            <a href="/docs">Open Swagger API Documentation</a>
        </div>

        <div class="card">
            <h2>Response</h2>
            <div id="output">Application ready.</div>
        </div>

    </main>

    <script>

    const API = "";

    async function request(url, method="GET", body=null) {
        const options = { method };

        if (body !== null) {
            options.headers = {
                "Content-Type": "application/json"
            };
            options.body = JSON.stringify(body);
        }

        const response = await fetch(API + url, options);
        const data = await response.json();

        document.getElementById("output").textContent =
            JSON.stringify(data, null, 2);

        if (!response.ok) {
            throw new Error(data.detail || "Request failed");
        }

        return data;
    }

    async function registerCustomer() {
        try {
            const result = await request(
                "/customers",
                "POST",
                {
                    name: customerName.value,
                    email: customerEmail.value,
                    phone: customerPhone.value
                }
            );

            customerId.value = result.customer_id;
            alert("Customer registered. ID: " + result.customer_id);

        } catch (error) {
            alert(error.message);
        }
    }

    async function loadRestaurants() {
        try {
            const data = await request("/restaurants");

            restaurants.innerHTML = data.map(r => `
                <div class="restaurant">
                    <h3>${r.name}</h3>
                    <p>${r.cuisine} | ${r.address}</p>
                    <p>Restaurant ID: ${r.id}</p>
                    <p>${r.is_open ? "Open" : "Closed"}</p>
                    <button onclick="showMenu(${r.id})">
                        View Menu
                    </button>
                </div>
            `).join("");

        } catch (error) {
            alert(error.message);
        }
    }

    async function showMenu(id) {
        try {
            const data = await request("/restaurants/" + id);

            restaurantId.value = id;

            restaurants.innerHTML += `
                <h3>Menu - ${data.name}</h3>
                ${data.menu.map(item => `
                    <div class="restaurant">
                        <b>${item.name}</b>
                        <p>${item.description}</p>
                        <p>Price: ₹${item.price}</p>
                        <p>Menu Item ID: ${item.id}</p>
                    </div>
                `).join("")}
            `;

        } catch (error) {
            alert(error.message);
        }
    }

    async function addToCart() {
        try {
            const data = await request(
                "/cart/add",
                "POST",
                {
                    customer_id: Number(customerId.value),
                    restaurant_id: Number(restaurantId.value),
                    menu_item_id: Number(menuId.value),
                    quantity: Number(quantity.value)
                }
            );

            alert(data.message);

        } catch (error) {
            alert(error.message);
        }
    }

    async function viewCart() {
        try {
            const data = await request(
                "/cart/" + customerId.value
            );

            cart.textContent = JSON.stringify(data, null, 2);

        } catch (error) {
            alert(error.message);
        }
    }

    async function checkout() {
        try {
            const data = await request(
                "/checkout",
                "POST",
                {
                    customer_id: Number(customerId.value),
                    delivery_address: deliveryAddress.value
                }
            );

            orderResult.textContent =
                "Order ID: " + data.order_id +
                " | Total: ₹" + data.total_amount;

            trackOrderId.value = data.order_id;

            alert("Order placed successfully!");

        } catch (error) {
            alert(error.message);
        }
    }

    async function trackOrder() {
        try {
            const data = await request(
                "/orders/" + trackOrderId.value + "/track"
            );

            tracking.textContent = JSON.stringify(data, null, 2);

        } catch (error) {
            alert(error.message);
        }
    }

    function connectTracking() {
        const id = trackOrderId.value;

        if (!id) {
            alert("Enter an order ID");
            return;
        }

        const protocol =
            location.protocol === "https:" ? "wss://" : "ws://";

        const socket = new WebSocket(
            protocol + location.host + "/ws/orders/" + id
        );

        socket.onopen = () => {
            tracking.textContent = "Live tracking connected.";
        };

        socket.onmessage = (event) => {
            const data = JSON.parse(event.data);

            tracking.textContent =
                "LIVE STATUS: " + data.status +
                "\\nUpdated: " + data.updated_at;
        };

        socket.onclose = () => {
            console.log("Tracking disconnected");
        };
    }

    </script>

    </body>
    </html>
    """


# ============================================================
# 8. RESTAURANT MANAGEMENT
# ============================================================

@app.post("/restaurants")
def create_restaurant(data: RestaurantCreate):

    db = SessionLocal()

    try:
        restaurant = Restaurant(**data.model_dump())

        db.add(restaurant)
        db.commit()
        db.refresh(restaurant)

        return {
            "message": "Restaurant registered successfully",
            "restaurant_id": restaurant.id
        }

    finally:
        db.close()


@app.get("/restaurants")
def get_restaurants():

    db = SessionLocal()

    try:
        restaurants = db.query(Restaurant).all()

        return [
            {
                "id": r.id,
                "name": r.name,
                "address": r.address,
                "phone": r.phone,
                "cuisine": r.cuisine,
                "is_open": r.is_open
            }
            for r in restaurants
        ]

    finally:
        db.close()


@app.get("/restaurants/{restaurant_id}")
def get_restaurant(restaurant_id: int):

    db = SessionLocal()

    try:
        restaurant = db.query(Restaurant).filter(
            Restaurant.id == restaurant_id
        ).first()

        if not restaurant:
            raise HTTPException(404, "Restaurant not found")

        return {
            "id": restaurant.id,
            "name": restaurant.name,
            "address": restaurant.address,
            "cuisine": restaurant.cuisine,
            "is_open": restaurant.is_open,
            "menu": [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "price": item.price,
                    "available": item.available
                }
                for item in restaurant.menu_items
            ]
        }

    finally:
        db.close()


@app.put("/restaurants/{restaurant_id}")
def update_restaurant(
    restaurant_id: int,
    data: RestaurantCreate
):

    db = SessionLocal()

    try:
        restaurant = db.query(Restaurant).filter(
            Restaurant.id == restaurant_id
        ).first()

        if not restaurant:
            raise HTTPException(404, "Restaurant not found")

        for key, value in data.model_dump().items():
            setattr(restaurant, key, value)

        db.commit()

        return {"message": "Restaurant updated"}

    finally:
        db.close()


@app.put("/restaurants/{restaurant_id}/availability")
def restaurant_availability(
    restaurant_id: int,
    is_open: bool
):

    db = SessionLocal()

    try:
        restaurant = db.query(Restaurant).filter(
            Restaurant.id == restaurant_id
        ).first()

        if not restaurant:
            raise HTTPException(404, "Restaurant not found")

        restaurant.is_open = is_open
        db.commit()

        return {"message": "Restaurant availability updated"}

    finally:
        db.close()


# ============================================================
# 9. MENU MANAGEMENT
# ============================================================

@app.post("/restaurants/{restaurant_id}/menu")
def add_menu_item(
    restaurant_id: int,
    data: MenuCreate
):

    db = SessionLocal()

    try:
        restaurant = db.query(Restaurant).filter(
            Restaurant.id == restaurant_id
        ).first()

        if not restaurant:
            raise HTTPException(404, "Restaurant not found")

        item = MenuItem(
            restaurant_id=restaurant_id,
            **data.model_dump()
        )

        db.add(item)
        db.commit()
        db.refresh(item)

        return {
            "message": "Menu item added",
            "menu_item_id": item.id
        }

    finally:
        db.close()


@app.put("/menu/{item_id}")
def update_menu_item(item_id: int, data: MenuCreate):

    db = SessionLocal()

    try:
        item = db.query(MenuItem).filter(
            MenuItem.id == item_id
        ).first()

        if not item:
            raise HTTPException(404, "Menu item not found")

        for key, value in data.model_dump().items():
            setattr(item, key, value)

        db.commit()

        return {"message": "Menu item updated"}

    finally:
        db.close()


@app.delete("/menu/{item_id}")
def delete_menu_item(item_id: int):

    db = SessionLocal()

    try:
        item = db.query(MenuItem).filter(
            MenuItem.id == item_id
        ).first()

        if not item:
            raise HTTPException(404, "Menu item not found")

        db.delete(item)
        db.commit()

        return {"message": "Menu item deleted"}

    finally:
        db.close()


# ============================================================
# 10. CUSTOMER MANAGEMENT
# ============================================================

@app.post("/customers")
def create_customer(data: CustomerCreate):

    db = SessionLocal()

    try:
        existing = db.query(Customer).filter(
            Customer.email == data.email
        ).first()

        if existing:
            raise HTTPException(400, "Email already registered")

        customer = Customer(**data.model_dump())

        db.add(customer)
        db.commit()
        db.refresh(customer)

        return {
            "message": "Customer registered",
            "customer_id": customer.id
        }

    finally:
        db.close()


@app.get("/customers")
def get_customers():

    db = SessionLocal()

    try:
        customers = db.query(Customer).all()

        return [
            {
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "phone": c.phone
            }
            for c in customers
        ]

    finally:
        db.close()


# ============================================================
# 11. CART MANAGEMENT
# ============================================================

@app.post("/cart/add")
def add_to_cart(
    data: dict
):

    db = SessionLocal()

    try:
        customer_id = int(data["customer_id"])
        restaurant_id = int(data["restaurant_id"])
        menu_item_id = int(data["menu_item_id"])
        quantity = int(data["quantity"])

        if quantity <= 0:
            raise HTTPException(400, "Quantity must be positive")

        customer = db.query(Customer).filter(
            Customer.id == customer_id
        ).first()

        restaurant = db.query(Restaurant).filter(
            Restaurant.id == restaurant_id
        ).first()

        menu = db.query(MenuItem).filter(
            MenuItem.id == menu_item_id,
            MenuItem.restaurant_id == restaurant_id
        ).first()

        if not customer:
            raise HTTPException(404, "Customer not found")

        if not restaurant:
            raise HTTPException(404, "Restaurant not found")

        if not restaurant.is_open:
            raise HTTPException(400, "Restaurant is closed")

        if not menu or not menu.available:
            raise HTTPException(404, "Available menu item not found")

        cart = db.query(Cart).filter(
            Cart.customer_id == customer_id
        ).first()

        if cart and cart.restaurant_id != restaurant_id:
            raise HTTPException(
                400,
                "Cart contains another restaurant's items. Clear it first."
            )

        if not cart:
            cart = Cart(
                customer_id=customer_id,
                restaurant_id=restaurant_id
            )

            db.add(cart)
            db.flush()

        item = db.query(CartItem).filter(
            CartItem.cart_id == cart.id,
            CartItem.menu_item_id == menu_item_id
        ).first()

        if item:
            item.quantity += quantity
        else:
            db.add(CartItem(
                cart_id=cart.id,
                menu_item_id=menu_item_id,
                quantity=quantity
            ))

        db.commit()

        return {"message": "Item added to cart"}

    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, "Invalid cart request")

    finally:
        db.close()


@app.get("/cart/{customer_id}")
def view_cart(customer_id: int):

    db = SessionLocal()

    try:
        cart = db.query(Cart).filter(
            Cart.customer_id == customer_id
        ).first()

        if not cart:
            return {
                "customer_id": customer_id,
                "items": [],
                "total": 0
            }

        return get_cart_dict(cart, db)

    finally:
        db.close()


@app.delete("/cart/{customer_id}")
def clear_cart(customer_id: int):

    db = SessionLocal()

    try:
        cart = db.query(Cart).filter(
            Cart.customer_id == customer_id
        ).first()

        if not cart:
            return {"message": "Cart is already empty"}

        db.query(CartItem).filter(
            CartItem.cart_id == cart.id
        ).delete()

        db.delete(cart)
        db.commit()

        return {"message": "Cart cleared"}

    finally:
        db.close()


# ============================================================
# 12. CHECKOUT AND ORDER PLACEMENT
# ============================================================

@app.post("/checkout")
def checkout(data: CheckoutRequest):

    db = SessionLocal()

    try:
        customer = db.query(Customer).filter(
            Customer.id == data.customer_id
        ).first()

        if not customer:
            raise HTTPException(404, "Customer not found")

        cart = db.query(Cart).filter(
            Cart.customer_id == data.customer_id
        ).first()

        if not cart:
            raise HTTPException(400, "Cart is empty")

        restaurant = db.query(Restaurant).filter(
            Restaurant.id == cart.restaurant_id
        ).first()

        if not restaurant or not restaurant.is_open:
            raise HTTPException(400, "Restaurant is unavailable")

        cart_items = db.query(CartItem).filter(
            CartItem.cart_id == cart.id
        ).all()

        if not cart_items:
            raise HTTPException(400, "Cart is empty")

        total = 0
        validated_items = []

        for cart_item in cart_items:

            menu = db.query(MenuItem).filter(
                MenuItem.id == cart_item.menu_item_id
            ).first()

            if not menu or not menu.available:
                raise HTTPException(
                    400,
                    "A cart item is no longer available"
                )

            subtotal = menu.price * cart_item.quantity
            total += subtotal

            validated_items.append({
                "menu_id": menu.id,
                "name": menu.name,
                "quantity": cart_item.quantity,
                "price": menu.price
            })

        order = Order(
            customer_id=data.customer_id,
            restaurant_id=cart.restaurant_id,
            total_amount=round(total, 2),
            delivery_address=data.delivery_address,
            status="PLACED",
            payment_status="PENDING"
        )

        db.add(order)
        db.flush()

        for item in validated_items:
            db.add(OrderItem(
                order_id=order.id,
                menu_item_id=item["menu_id"],
                item_name=item["name"],
                quantity=item["quantity"],
                price=item["price"]
            ))

        db.query(CartItem).filter(
            CartItem.cart_id == cart.id
        ).delete()

        db.delete(cart)
        db.commit()
        db.refresh(order)

        return {
            "message": "Order placed successfully",
            "order_id": order.id,
            "total_amount": order.total_amount,
            "status": order.status,
            "payment_status": order.payment_status
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@app.get("/orders")
def get_orders():

    db = SessionLocal()

    try:
        orders = db.query(Order).order_by(
            Order.created_at.desc()
        ).all()

        return [get_order_dict(order) for order in orders]

    finally:
        db.close()


@app.get("/orders/customer/{customer_id}")
def customer_order_history(customer_id: int):

    db = SessionLocal()

    try:
        orders = db.query(Order).filter(
            Order.customer_id == customer_id
        ).order_by(Order.created_at.desc()).all()

        return [get_order_dict(order) for order in orders]

    finally:
        db.close()


@app.get("/orders/{order_id}")
def get_order(order_id: int):

    db = SessionLocal()

    try:
        order = db.query(Order).filter(
            Order.id == order_id
        ).first()

        if not order:
            raise HTTPException(404, "Order not found")

        return get_order_dict(order)

    finally:
        db.close()


# ============================================================
# 13. DELIVERY PARTNER MANAGEMENT
# ============================================================

@app.post("/partners")
def create_partner(data: PartnerCreate):

    db = SessionLocal()

    try:
        partner = DeliveryPartner(
            name=data.name,
            phone=data.phone,
            available=True
        )

        db.add(partner)
        db.commit()
        db.refresh(partner)

        return {
            "message": "Delivery partner registered",
            "partner_id": partner.id
        }

    finally:
        db.close()


@app.get("/partners")
def get_partners():

    db = SessionLocal()

    try:
        partners = db.query(DeliveryPartner).all()

        return [
            {
                "id": p.id,
                "name": p.name,
                "phone": p.phone,
                "available": p.available
            }
            for p in partners
        ]

    finally:
        db.close()


@app.get("/partners/{partner_id}/dashboard")
def partner_dashboard(partner_id: int):

    db = SessionLocal()

    try:
        partner = db.query(DeliveryPartner).filter(
            DeliveryPartner.id == partner_id
        ).first()

        if not partner:
            raise HTTPException(404, "Partner not found")

        orders = db.query(Order).filter(
            Order.delivery_partner_id == partner_id
        ).all()

        return {
            "partner": {
                "id": partner.id,
                "name": partner.name,
                "phone": partner.phone,
                "available": partner.available
            },
            "orders": [
                get_order_dict(order)
                for order in orders
            ]
        }

    finally:
        db.close()


# ============================================================
# 14. DELIVERY PARTNER ASSIGNMENT
# ============================================================

@app.post("/orders/{order_id}/assign/{partner_id}")
def assign_partner(order_id: int, partner_id: int):

    db = SessionLocal()

    try:
        order = db.query(Order).filter(
            Order.id == order_id
        ).first()

        partner = db.query(DeliveryPartner).filter(
            DeliveryPartner.id == partner_id
        ).first()

        if not order:
            raise HTTPException(404, "Order not found")

        if not partner:
            raise HTTPException(404, "Partner not found")

        if not partner.available:
            raise HTTPException(400, "Partner unavailable")

        if order.delivery_partner_id is not None:
            raise HTTPException(400, "Partner already assigned")

        if order.status in ["DELIVERED", "CANCELLED"]:
            raise HTTPException(400, "Order is closed")

        order.delivery_partner_id = partner.id
        order.status = "CONFIRMED"
        partner.available = False

        db.commit()

        return {
            "message": "Delivery partner assigned",
            "order_id": order.id,
            "partner_id": partner.id
        }

    finally:
        db.close()


# ============================================================
# 15. ORDER STATUS AND REAL-TIME TRACKING
# ============================================================

@app.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    data: StatusUpdate
):

    db = SessionLocal()

    try:
        status = data.status.upper()

        if status not in VALID_STATUSES:
            raise HTTPException(400, "Invalid order status")

        order = db.query(Order).filter(
            Order.id == order_id
        ).first()

        if not order:
            raise HTTPException(404, "Order not found")

        if order.status in ["DELIVERED", "CANCELLED"]:
            raise HTTPException(400, "Order already closed")

        if status == "DELIVERED" and not order.delivery_partner_id:
            raise HTTPException(
                400,
                "Assign a delivery partner before delivery"
            )

        order.status = status
        order.updated_at = datetime.utcnow()

        if status in ["DELIVERED", "CANCELLED"]:
            if order.delivery_partner_id:
                partner = db.query(DeliveryPartner).filter(
                    DeliveryPartner.id == order.delivery_partner_id
                ).first()

                if partner:
                    partner.available = True

        db.commit()

        result = {
            "order_id": order.id,
            "status": order.status,
            "updated_at": order.updated_at.isoformat()
        }

    finally:
        db.close()

    await manager.broadcast(order_id, result)

    return {
        "message": "Order status updated",
        **result
    }


@app.get("/orders/{order_id}/track")
def track_order(order_id: int):

    db = SessionLocal()

    try:
        order = db.query(Order).filter(
            Order.id == order_id
        ).first()

        if not order:
            raise HTTPException(404, "Order not found")

        partner = None

        if order.delivery_partner_id:
            partner = db.query(DeliveryPartner).filter(
                DeliveryPartner.id == order.delivery_partner_id
            ).first()

        return {
            "order_id": order.id,
            "status": order.status,
            "payment_status": order.payment_status,
            "delivery_address": order.delivery_address,
            "delivery_partner": (
                {
                    "id": partner.id,
                    "name": partner.name,
                    "phone": partner.phone
                }
                if partner else None
            ),
            "updated_at": order.updated_at.isoformat()
        }

    finally:
        db.close()


@app.websocket("/ws/orders/{order_id}")
async def websocket_tracking(
    websocket: WebSocket,
    order_id: int
):

    db = SessionLocal()

    try:
        order = db.query(Order).filter(
            Order.id == order_id
        ).first()

        if not order:
            await websocket.close(code=1008)
            return

    finally:
        db.close()

    await manager.connect(order_id, websocket)

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(order_id, websocket)


# ============================================================
# 16. PAYMENT PROCESSING - DEMONSTRATION MODE
# ============================================================

@app.post("/payments")
def process_payment(data: PaymentRequest):

    db = SessionLocal()

    try:
        order = db.query(Order).filter(
            Order.id == data.order_id
        ).first()

        if not order:
            raise HTTPException(404, "Order not found")

        if order.status == "CANCELLED":
            raise HTTPException(400, "Order is cancelled")

        if order.payment_status == "PAID":
            raise HTTPException(400, "Order already paid")

        method = data.method.upper()

        if method not in ["UPI", "CARD", "CASH"]:
            raise HTTPException(400, "Invalid payment method")

        payment = Payment(
            order_id=order.id,
            amount=order.total_amount,
            method=method,
            status="SUCCESS",
            transaction_id=(
                f"DEMO-{order.id}-{int(datetime.utcnow().timestamp())}"
            )
        )

        order.payment_status = "PAID"

        db.add(payment)
        db.commit()
        db.refresh(payment)

        return {
            "message": "Demo payment successful",
            "payment_id": payment.id,
            "transaction_id": payment.transaction_id,
            "amount": payment.amount,
            "method": payment.method,
            "status": payment.status
        }

    finally:
        db.close()


@app.get("/payments/order/{order_id}")
def payment_history(order_id: int):

    db = SessionLocal()

    try:
        payments = db.query(Payment).filter(
            Payment.order_id == order_id
        ).all()

        return [
            {
                "id": p.id,
                "amount": p.amount,
                "method": p.method,
                "status": p.status,
                "transaction_id": p.transaction_id,
                "created_at": p.created_at.isoformat()
            }
            for p in payments
        ]

    finally:
        db.close()


# ============================================================
# 17. CUSTOMER FEEDBACK AND RESTAURANT RATINGS
# ============================================================

@app.post("/reviews")
def create_review(data: ReviewCreate):

    db = SessionLocal()

    try:
        customer = db.query(Customer).filter(
            Customer.id == data.customer_id
        ).first()

        restaurant = db.query(Restaurant).filter(
            Restaurant.id == data.restaurant_id
        ).first()

        if not customer:
            raise HTTPException(404, "Customer not found")

        if not restaurant:
            raise HTTPException(404, "Restaurant not found")

        delivered_order = db.query(Order).filter(
            Order.customer_id == data.customer_id,
            Order.restaurant_id == data.restaurant_id,
            Order.status == "DELIVERED"
        ).first()

        if not delivered_order:
            raise HTTPException(
                400,
                "Review allowed after a delivered order"
            )

        existing = db.query(Review).filter(
            Review.customer_id == data.customer_id,
            Review.restaurant_id == data.restaurant_id
        ).first()

        if existing:
            raise HTTPException(
                400,
                "You have already reviewed this restaurant"
            )

        review = Review(
            customer_id=data.customer_id,
            restaurant_id=data.restaurant_id,
            rating=data.rating,
            comment=data.comment
        )

        db.add(review)
        db.commit()
        db.refresh(review)

        return {
            "message": "Review submitted successfully",
            "review_id": review.id
        }

    finally:
        db.close()


@app.get("/restaurants/{restaurant_id}/reviews")
def get_reviews(restaurant_id: int):

    db = SessionLocal()

    try:
        reviews = db.query(Review).filter(
            Review.restaurant_id == restaurant_id
        ).all()

        average = db.query(
            func.avg(Review.rating)
        ).filter(
            Review.restaurant_id == restaurant_id
        ).scalar()

        return {
            "restaurant_id": restaurant_id,
            "average_rating": round(float(average or 0), 2),
            "total_reviews": len(reviews),
            "reviews": [
                {
                    "customer_id": r.customer_id,
                    "rating": r.rating,
                    "comment": r.comment,
                    "created_at": r.created_at.isoformat()
                }
                for r in reviews
            ]
        }

    finally:
        db.close()


# ============================================================
# 18. RESTAURANT ANALYTICS
# ============================================================

@app.get("/analytics/restaurants/{restaurant_id}")
def restaurant_analytics(restaurant_id: int):

    db = SessionLocal()

    try:
        restaurant = db.query(Restaurant).filter(
            Restaurant.id == restaurant_id
        ).first()

        if not restaurant:
            raise HTTPException(404, "Restaurant not found")

        orders = db.query(Order).filter(
            Order.restaurant_id == restaurant_id
        ).all()

        delivered = [
            order for order in orders
            if order.status == "DELIVERED"
        ]

        revenue = sum(
            order.total_amount
            for order in delivered
            if order.payment_status == "PAID"
        )

        average_rating = db.query(
            func.avg(Review.rating)
        ).filter(
            Review.restaurant_id == restaurant_id
        ).scalar() or 0

        return {
            "restaurant": restaurant.name,
            "total_orders": len(orders),
            "delivered_orders": len(delivered),
            "pending_orders": sum(
                1 for order in orders
                if order.status not in ["DELIVERED", "CANCELLED"]
            ),
            "revenue": round(revenue, 2),
            "average_rating": round(float(average_rating), 2)
        }

    finally:
        db.close()


# ============================================================
# 19. PLATFORM ANALYTICS DASHBOARD
# ============================================================

@app.get("/analytics/platform")
def platform_analytics():

    db = SessionLocal()

    try:
        total_restaurants = db.query(Restaurant).count()
        total_customers = db.query(Customer).count()
        total_partners = db.query(DeliveryPartner).count()
        total_orders = db.query(Order).count()

        delivered_orders = db.query(Order).filter(
            Order.status == "DELIVERED"
        ).count()

        pending_orders = db.query(Order).filter(
            Order.status.notin_(["DELIVERED", "CANCELLED"])
        ).count()

        revenue = db.query(
            func.sum(Order.total_amount)
        ).filter(
            Order.status == "DELIVERED",
            Order.payment_status == "PAID"
        ).scalar() or 0

        return {
            "total_restaurants": total_restaurants,
            "total_customers": total_customers,
            "total_delivery_partners": total_partners,
            "total_orders": total_orders,
            "delivered_orders": delivered_orders,
            "pending_orders": pending_orders,
            "total_revenue": round(float(revenue), 2)
        }

    finally:
        db.close()


# ============================================================
# 20. HEALTH CHECK
# ============================================================

@app.get("/health")
def health_check():

    return {
        "status": "running",
        "application": "Food Ordering and Delivery Platform",
        "database": "MySQL"
    }
