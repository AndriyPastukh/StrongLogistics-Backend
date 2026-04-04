from django.core.management.base import BaseCommand
from logistics.models import Material, Location, Inventory, Vehicle, Order, OrderItem
import random

class Command(BaseCommand):
    help = 'Populates the database with realistic mock data for testing advanced logistics V4'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Clearing existing data...'))
        OrderItem.objects.all().delete()
        Order.objects.all().delete()
        Inventory.objects.all().delete()
        Vehicle.objects.all().delete()
        Location.objects.all().delete()
        Material.objects.all().delete()

        # 1. Create Materials
        self.stdout.write('Creating materials...')
        materials = [
            Material.objects.create(name="Concrete Blocks", unit="pallet"),
            Material.objects.create(name="Steel Rebar", unit="ton"),
            Material.objects.create(name="Glass Panels", unit="box"),
            Material.objects.create(name="Medical Supplies", unit="crate")
        ]

        # 2. Create Locations
        self.stdout.write('Creating locations...')
        
        # Central Hub
        hub = Location.objects.create(
            name="Main Logistics Hub (Kyiv)", 
            latitude=50.4501, longitude=30.5234, 
            location_type='warehouse', 
            service_time_sec=600
        )
        
        # Suppliers (Pickups)
        suppliers = []
        supplier_data = [
            ("Alpha Steel Works", 50.40, 30.60),
            ("Beta Construction Supplies", 50.50, 30.40),
            ("Gamma Medical Logistics", 50.45, 30.30)
        ]
        for name, lat, lng in supplier_data:
            s = Location.objects.create(
                name=name, latitude=lat, longitude=lng,
                location_type='supplier',
                service_time_sec=900,
                time_window_start=28800, # 08:00
                time_window_end=64800    # 18:00
            )
            suppliers.append(s)
            # Add inventory to suppliers
            for mat in materials:
                Inventory.objects.create(location=s, material=mat, quantity=500.0)

        # Customers (Deliveries)
        customers = []
        customer_data = [
            ("Residential Site A", 50.42, 30.55),
            ("Office Complex B", 50.48, 30.45),
            ("Hospital C", 50.44, 30.51),
            ("Bridge Construction D", 50.41, 30.49),
            ("School Site E", 50.46, 30.54)
        ]
        for name, lat, lng in customer_data:
            c = Location.objects.create(
                name=name, latitude=lat, longitude=lng,
                location_type='customer',
                service_time_sec=300,
                time_window_start=32400, # 09:00
                time_window_end=72000    # 20:00
            )
            customers.append(c)
        
        # 3. Add Hub Inventory
        for mat in materials:
            Inventory.objects.create(location=hub, material=mat, quantity=1000.0)

        # 4. Create Vehicles
        self.stdout.write('Creating vehicles...')
        vehicle_configs = [
            ("Heavy Truck 01", 50.0, 10000.0), # Volume, Weight
            ("Medium Van 02", 20.0, 3500.0),
            ("Service Truck 03", 30.0, 5000.0)
        ]
        vehicles = []
        for name, vol, weight in vehicle_configs:
            v = Vehicle.objects.create(
                name=name, capacity=vol, weight_capacity=weight,
                current_location=hub, start_depot=hub, end_depot=hub,
                cost_per_km=1.5
            )
            vehicles.append(v)
            
        # 5. Create Orders (Pending)
        self.stdout.write('Creating orders...')
        priorities = ['normal', 'high', 'critical']
        for i in range(8):
            dest = random.choice(customers)
            pickup = random.choice(suppliers)
            mat = random.choice(materials)
            qty = random.randint(1, 10)
            
            o = Order.objects.create(
                destination=dest,
                assigned_warehouse=pickup,
                priority=random.choice(priorities),
                weight=qty * 50.0, # 50kg per unit
                time_window_start=36000, # 10:00
                time_window_end=64800,   # 18:00
                status='pending'
            )
            OrderItem.objects.create(
                order=o, material=mat, quantity=qty
            )

        self.stdout.write(self.style.SUCCESS(f'Successfully populated V4 Mock Data:'))
        self.stdout.write(f'- {Location.objects.count()} Locations')
        self.stdout.write(f'- {Vehicle.objects.count()} Vehicles')
        self.stdout.write(f'- {Order.objects.count()} Pending Orders')
