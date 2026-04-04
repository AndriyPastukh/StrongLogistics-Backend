from rest_framework import serializers
from .models import Material, Location, Inventory, Vehicle, Order, OrderItem

class MaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = '__all__'

class InventorySerializer(serializers.ModelSerializer):
    material_name = serializers.ReadOnlyField(source='material.name')
    
    class Meta:
        model = Inventory
        fields = ['id', 'location', 'material', 'material_name', 'quantity']

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ['id', 'name', 'latitude', 'longitude', 'location_type', 'service_time_sec', 'time_window_start', 'time_window_end']

class VehicleSerializer(serializers.ModelSerializer):
    location_name = serializers.ReadOnlyField(source='current_location.name')
    
    class Meta:
        model = Vehicle
        fields = [
            'id', 'name', 'capacity', 'weight_capacity', 'current_location', 
            'location_name', 'start_depot', 'end_depot', 'last_lat', 
            'last_lng', 'is_online', 'cost_per_km'
        ]

class OrderItemSerializer(serializers.ModelSerializer):
    material_name = serializers.ReadOnlyField(source='material.name')
    unit = serializers.ReadOnlyField(source='material.unit')

    class Meta:
        model = OrderItem
        fields = ['id', 'material', 'material_name', 'quantity', 'unit']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    destination_name = serializers.ReadOnlyField(source='destination.name')
    assigned_warehouse_name = serializers.ReadOnlyField(source='assigned_warehouse.name')
    assigned_vehicle_name = serializers.ReadOnlyField(source='assigned_vehicle.name')
    
    class Meta:
        model = Order
        fields = [
            'id', 'created_at', 'destination', 'destination_name', 
            'assigned_warehouse', 'assigned_warehouse_name', 
            'assigned_vehicle', 'assigned_vehicle_name', 
            'priority', 'status', 'weight', 'time_window_start', 
            'time_window_end', 'items'
        ]
