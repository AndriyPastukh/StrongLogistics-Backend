from django.contrib import admin
from .models import Material, Location, Inventory, Vehicle, Order, OrderItem

class InventoryInline(admin.TabularInline):
    model = Inventory
    extra = 1

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'location_type', 'latitude', 'longitude')
    list_filter = ('location_type',)
    inlines = [InventoryInline]

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'location', 'material', 'quantity')
    list_filter = ('location', 'material')

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'capacity', 'current_location')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'destination', 'priority', 'status')
    list_filter = ('priority', 'status')
    inlines = [OrderItemInline]

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'material', 'quantity')
