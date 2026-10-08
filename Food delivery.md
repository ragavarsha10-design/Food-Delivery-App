# 🍔 Food Ordering & Delivery Application

A complete **Food Ordering and Delivery Application** built using **FastAPI** and **MySQL**.

The application allows customers to browse restaurants, view menus, add food items to a cart, place orders, make payments, track orders, and provide reviews.

It also provides features for restaurant management, delivery partner management, real-time order tracking, and analytics.

---

## 🚀 Features

### 1. Restaurant Management
- Register restaurants
- View all restaurants
- View restaurant details
- Update restaurant information
- Enable/disable restaurant availability
- Manage restaurant menus
- Add menu items
- Update menu items
- Delete menu items

### 2. Customer Management
- Register customers
- View customers
- Customer-specific shopping cart
- View order history

### 3. Order Placement
- Add food items to cart
- View cart
- Update cart quantity
- Clear cart
- Checkout
- Automatically calculate order total
- Create orders from cart
- View order details
- View customer order history

### 4. Real-Time Order Tracking
Customers can track their order using different order statuses:

```text
PLACED
   ↓
CONFIRMED
   ↓
PREPARING
   ↓
READY_FOR_PICKUP
   ↓
PICKED_UP
   ↓
OUT_FOR_DELIVERY
   ↓
DELIVERED
