from django.core.management.base import BaseCommand
from logistics.models import Material, Location, Inventory, Vehicle, Order, OrderItem
import random

class Command(BaseCommand):
    help = 'Populates the database with realistic mock data for testing logistics system'

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
            Material.objects.create(name='Water'),
            Material.objects.create(name='Food Rations'),
            Material.objects.create(name='Medical Supplies'),
        ]

        # 2. Create Locations
        self.stdout.write('Creating locations...')
        # Depot in Stryi, Ukraine (Strategic Logistics hub)
        depot = Location.objects.create(
            name='Central Depot - Stryi',
            location_type='warehouse',
            latitude=49.2558,
            longitude=23.8510
        )

        # 7 Dropoff points around Stryi/Lviv region
        dropoffs = []
        dropoff_data = [
            ("Lviv Regional Point", 49.8397, 24.0297),
            ("Drogobych Hub", 49.3508, 23.5061),
            ("Sambir Distribution", 49.5183, 23.1975),
            ("Truskavets Center", 49.2785, 23.5050),
            ("Kalush Station", 49.0275, 24.3600),
            ("Ivano-Frankivsk Post", 48.9226, 24.7111),
            ("Morshyn Aid Station", 49.1550, 23.8700),
        ]

        for name, lat, lon in dropoff_data:
            dropoffs.append(Location.objects.create(
                name=name,
                location_type='dropoff',
                latitude=lat,
                longitude=lon
            ))

        # 3. Add Inventory to Depot
        for material in materials:
            Inventory.objects.create(
                location=depot,
                material=material,
                quantity=10000.0  # Sufficient stock for testing
            )

        # 4. Create Vehicles
        self.stdout.write('Creating vehicles...')
        vehicle_configs = [
            ("Light Truck A", 50.0),
            ("Medium Truck B", 100.0),
            ("Heavy Carrier C", 150.0),
        ]
        for name, cap in vehicle_configs:
            Vehicle.objects.create(
                name=name,
                capacity=cap,
                current_location=depot
            )

        # 5. Create Orders
        self.stdout.write('Creating orders...')
        for i in range(10):
            priority = 'normal'
            if i < 2:
                priority = 'critical'
            elif i < 4:
                priority = 'high'
            
            order = Order.objects.create(
                destination=random.choice(dropoffs),
                priority=priority,
                status='pending'
            )

            # 1-2 Items per order
            num_items = random.randint(1, 2)
            for mat in random.sample(materials, num_items):
                OrderItem.objects.create(
                    order=order,
                    material=mat,
                    quantity=round(random.uniform(5.0, 25.0), 2)
                )

        self.stdout.write(self.style.SUCCESS('Successfully populated mock data:'))
        self.stdout.write(f'- {Material.objects.count()} Materials created')
        self.stdout.write(f'- {Location.objects.count()} Locations created (1 Warehouse, 7 Dropoffs)')
        self.stdout.write(f'- {Vehicle.objects.count()} Vehicles created')
        self.stdout.write(f'- {Order.objects.count()} Orders created (2 critical, 2 high, 6 normal)')
