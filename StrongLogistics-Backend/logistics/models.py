from django.db import models

class Material(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class Location(models.Model):
    LOCATION_TYPES = (
        ('supplier', 'Supplier'),
        ('warehouse', 'Warehouse'),
        ('dropoff', 'Dropoff'),
    )
    name = models.CharField(max_length=255)
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPES)
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return f"{self.name} ({self.get_location_type_display()})"

class Inventory(models.Model):
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='inventory')
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    quantity = models.FloatField(default=0)

    class Meta:
        verbose_name_plural = "Inventories"
        unique_together = ('location', 'material')

    def __str__(self):
        return f"{self.location.name} - {self.material.name}: {self.quantity}"

class Vehicle(models.Model):
    name = models.CharField(max_length=100)
    capacity = models.FloatField()
    current_location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True)
    last_lat = models.FloatField(null=True, blank=True)
    last_lng = models.FloatField(null=True, blank=True)
    is_online = models.BooleanField(default=False)

    def __str__(self):
        return self.name

class Order(models.Model):
    PRIORITY_CHOICES = (
        ('normal', 'Normal'),
        ('high', 'High'),
        ('critical', 'Critical'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('completed', 'Completed'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    destination = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='orders')
    assigned_warehouse = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_orders')
    assigned_vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_orders')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return f"Order #{self.id} - {self.destination.name}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    quantity = models.FloatField()

    def __str__(self):
        return f"{self.material.name} x {self.quantity}"
