from geopy.distance import geodesic
from ..models import Location, Inventory

def find_nearest_warehouse(lat, lon, material_id, required_qty):
    """
    Finds the nearest warehouse that has at least the required quantity of a specific material.
    """
    target_coords = (lat, lon)
    
    # Filter locations that are warehouses and have the required material stock
    warehouses_with_stock = Location.objects.filter(
        location_type='warehouse',
        inventory__material_id=material_id,
        inventory__quantity__gte=required_qty
    ).distinct()

    nearest_warehouse = None
    min_distance = float('inf')

    for warehouse in warehouses_with_stock:
        warehouse_coords = (warehouse.latitude, warehouse.longitude)
        distance = geodesic(target_coords, warehouse_coords).km
        
        if distance < min_distance:
            min_distance = distance
            nearest_warehouse = warehouse

    if nearest_warehouse:
        return {
            "id": nearest_warehouse.id,
            "name": nearest_warehouse.name,
            "latitude": nearest_warehouse.latitude,
            "longitude": nearest_warehouse.longitude,
            "distance_km": round(min_distance, 2)
        }
    
    return None
