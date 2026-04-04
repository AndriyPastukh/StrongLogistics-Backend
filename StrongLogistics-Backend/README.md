# 🚛 StrongLogistics Backend (Pro MVP)

### High-Performance AI-Driven Logistics Optimization Engine

StrongLogistics is a robust REST API designed for complex vehicle routing, inventory management, and real-time logistics analytics. Built for high-fidelity operations, it solves the **Capacitated Vehicle Routing Problem (CVRP)** with advanced constraints using Google OR-Tools.

---

## 🌟 Key Features

- **🎯 Advanced CVRP Solver**:
  - **Pickup & Delivery Pairs**: Chains suppliers and customer locations in optimal sequences.
  - **Multi-Constraint Optimization**: Respects both **Weight (kg)** and **Volume (m³)** vehicle capacities.
  - **Time Windows**: Ensures "Just-in-Time" deliveries with strict arrival/departure windows.
  - **Service Times**: Accounts for loading/unloading overhead at each stop.

- **📦 Inventory Management**:
  - Real-time stock tracking across multiple warehouses and suppliers.
  - **Atomic Transactions**: Prevents race conditions during simultaneous order completions.
  - **Nearest Stock Search**: Geo-spatial lookup for the closest warehouse with required materials.

- **📊 Dashboard & Analytics**:
  - Real-time KPIs: Active orders, fleet utilization, and critical stock alerts.
  - GPS Telemetry: Track vehicle coordinates and online status.

- **📄 Professional Reporting**:
  - Automatic PDF Driver Manifest generation with order details and priority markings.

- **🔐 Scalable Infrastructure**:
  - Secure JWT Authentication (Access/Refresh flow).
  - Clean RESTful architecture built with Django & DRF.

---

## 🛠️ Tech Stack

- **Core**: Python 3.11+, Django 5.2, DRF
- **AI/Math**: Google OR-Tools (Constraint Programming)
- **Database**: SQLite (Default for MVP) / PostgreSQL ready
- **Auth**: SimpleJWT
- **Geo**: Geopy (Haversine distances)
- **Reporting**: ReportLab (PDF Generation)

---

## 🚀 Getting Started

### 1. Installation
```bash
# Clone the repository
git clone <repo-url>
cd StrongLogistics-Backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Database Setup
```bash
python manage.py makemigrations
python manage.py migrate
```

### 3. Initialize Mock Data (Demo Mode)
Populate the system with a pre-configured logistics network:
```bash
python manage.py populate_mock_data
```

### 4. Run the Server
```bash
python manage.py runserver
```

---

## 🛣️ API Quick Start

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/orders/auto_assign/` | `POST` | **Killer Feature:** Triggers the OR-Tools solver to optimize routes. |
| `/api/analytics/` | `GET` | Returns real-time KPIs for the dashboard. |
| `/api/vehicles/{id}/sync_telemetry/` | `PATCH` | Update GPS coordinates and status. |
| `/api/vehicles/{id}/download_route_manifest/` | `GET` | Download PDF driver manifest. |
| `/api/orders/{id}/complete_order/` | `POST` | Atomically completes order and syncs inventory. |

---

## 🏆 Hackathon Demo Scenario

1. **Populate Data**: Run `populate_mock_data`.
2. **Trigger Optimization**: Call `auto_assign`. Watch the engine distribute 8+ orders across 3 vehicles, respecting all weight and time window constraints.
3. **Verify Results**: Check the rich route response containing step-by-step coordinates.
4. **Complete Cycle**: Call `complete_order` to see warehouse inventory update in real-time.

