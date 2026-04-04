from django.db import models

class Material(models.Model):
    name = models.CharField(max_length=100)
    unit = models.CharField(max_length=20, default='pcs')

    def __str__(self):
        return self.name

class Location(models.Model):
    LOCATION_TYPES = [
        ('warehouse', 'Warehouse / Depot'),
        ('supplier', 'Supplier / Pickup'),
        ('customer', 'Customer / Delivery'),
        ('hotspot', 'Priority Hotspot'),
    ]
    name = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPES, default='customer')
    service_time_sec = models.FloatField(default=0.0)
    time_window_start = models.FloatField(null=True, blank=True)
    time_window_end = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.location_type})"

class Inventory(models.Model):
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='inventory')
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    quantity = models.FloatField()

    class Meta:
        verbose_name_plural = "Inventories"
        unique_together = ('location', 'material')

    def __str__(self):
        return f"{self.location.name} - {self.material.name}: {self.quantity}"

class Vehicle(models.Model):
    name = models.CharField(max_length=100)
    capacity = models.FloatField()  # Volume (m3)
    weight_capacity = models.FloatField(default=1000.0) # Weight (kg)
    current_location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, related_name='current_vehicles')
    start_depot = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='starting_vehicles')
    end_depot = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='ending_vehicles')
    last_lat = models.FloatField(null=True, blank=True)
    last_lng = models.FloatField(null=True, blank=True)
    is_online = models.BooleanField(default=False)
    cost_per_km = models.FloatField(default=1.0)

    def __str__(self):
        return self.name

class Order(models.Model):
    PRIORITY_CHOICES = [
        ('normal', 'Normal'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('completed', 'Completed'),
    ]
    created_at = models.DateTimeField(auto_now_add=True)
    destination = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='orders')
    assigned_warehouse = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_orders')
    assigned_vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_orders')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    weight = models.FloatField(default=0.0)
    time_window_start = models.FloatField(null=True, blank=True)
    time_window_end = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"Order #{self.id} - {self.destination.name}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    quantity = models.FloatField()

    def __str__(self):
        return f"{self.material.name} x {self.quantity}"
