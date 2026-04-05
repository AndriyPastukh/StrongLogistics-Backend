import io
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import FileResponse
from rest_framework import viewsets, status, views, serializers
from rest_framework.decorators import action, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

from .models import Material, Location, Inventory, Vehicle, Order, OrderItem
from .serializers import (
    MaterialSerializer, LocationSerializer, InventorySerializer,
    VehicleSerializer, OrderSerializer, OrderItemSerializer
)
from .services.geo import find_nearest_warehouse
from .services.routing import RouteOptimizer

class MaterialViewSet(viewsets.ModelViewSet):
    queryset = Material.objects.all()
    serializer_class = MaterialSerializer

class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    filterset_fields = ['location_type']
    search_fields = ['name']

    @action(detail=False, methods=['get'])
    def nearest_stock(self, request):
        lat = request.query_params.get('lat')
        lon = request.query_params.get('lon')
        material_id = request.query_params.get('material_id')
        qty = request.query_params.get('qty', 1)

        if not all([lat, lon, material_id]):
            return Response({"error": "Missing params: lat, lon, material_id"},
                            status=status.HTTP_400_BAD_REQUEST)

        result = find_nearest_warehouse(float(lat), float(lon), int(material_id), float(qty))
        if result:
            return Response(result)
        return Response({"error": "No stock found nearby"}, status=status.HTTP_404_NOT_FOUND)

    @transaction.atomic
    @action(detail=True, methods=['post'])
    def create_task(self, request, pk=None):
        """Creates a new Order for this location with material items."""
        location = self.get_object()
        items_data = request.data.get('items', {})
        
        if not items_data or not isinstance(items_data, dict):
            return Response({"error": "Missing or invalid 'items' dictionary. Format: {'material_name': quantity}"}, 
                             status=status.HTTP_400_BAD_REQUEST)

        # Use default pickup location (the main warehouse/depot)
        warehouse = Location.objects.filter(location_type='warehouse').first()

        order = Order.objects.create(
            destination=location,
            assigned_warehouse=warehouse,
            status='pending'
        )
        
        for material_name, qty in items_data.items():
            material, _ = Material.objects.get_or_create(name=material_name)
            OrderItem.objects.create(order=order, material=material, quantity=float(qty))
        
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

class InventoryViewSet(viewsets.ModelViewSet):
    queryset = Inventory.objects.all()
    serializer_class = InventorySerializer
    filterset_fields = ['location', 'material']

class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer

    @action(detail=True, methods=['patch'])
    def sync_telemetry(self, request, pk=None):
        """Updates vehicle real-time GPS and status."""
        vehicle = self.get_object()
        lat = request.data.get('last_lat')
        lng = request.data.get('last_lng')
        online = request.data.get('is_online')

        if lat is not None: vehicle.last_lat = lat
        if lng is not None: vehicle.last_lng = lng
        if online is not None: vehicle.is_online = online

        vehicle.save()
        return Response(self.get_serializer(vehicle).data)

    @action(detail=True, methods=['post'])
    def add_to_route(self, request, pk=None):
        """Find a 'pending' order that has this pointId as a delivery location and assign it."""
        vehicle = self.get_object()
        point_id = request.data.get('pointId')
        
        if not point_id:
            return Response({"error": "Missing 'pointId'"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # Find an order that is pending and whose destination is the given pointId
            order = Order.objects.filter(destination_id=point_id, status='pending').first()
            if not order:
                 return Response({"error": f"No pending order found for location ID {point_id}"}, 
                                 status=status.HTTP_404_NOT_FOUND)

            order.assigned_vehicle = vehicle
            order.status = 'assigned'
            order.save()
            return Response({"status": "success", "order": OrderSerializer(order).data})
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get', 'post'])
    def get_optimized_route(self, request, pk=None):
        """Returns sequence of points for assigned orders, including full Location data and materials."""
        vehicle = self.get_object()
        orders = Order.objects.filter(assigned_vehicle=vehicle, status='assigned')
        
        if not orders.exists():
            return Response({"steps": [], "materials_summary": []})

        from .services.routing import SolverLocation, SolverOrder, SolverVehicle, RouteOptimizer
        
        locations = Location.objects.all()
        depot = vehicle.start_depot or Location.objects.filter(location_type='warehouse').first()

        s_locations = [
            SolverLocation(
                id=loc.id, name=loc.name, lat=loc.latitude, lng=loc.longitude, 
                type=loc.location_type, service_time_sec=loc.service_time_sec,
                time_window_start=loc.time_window_start, time_window_end=loc.time_window_end
            ) for loc in locations
        ]
        
        s_vehicles = [
            SolverVehicle(
                id=vehicle.id, start_depot_id=depot.id if depot else 1,
                end_depot_id=vehicle.end_depot.id if vehicle.end_depot else (depot.id if depot else 1),
                capacity=vehicle.capacity, weight_capacity=vehicle.weight_capacity,
                max_distance=500.0 # Enough range
            )
        ]
        
        s_orders = [
            SolverOrder(
                id=o.id, 
                from_location_id=o.assigned_warehouse.id if o.assigned_warehouse else (depot.id if depot else 1),
                to_location_id=o.destination.id,
                volume=sum(item.quantity for item in o.items.all()),
                weight=o.weight,
                priority=3 if o.priority == 'critical' else (2 if o.priority == 'high' else 1)
            ) for o in orders
        ]

        optimizer = RouteOptimizer(s_vehicles, s_orders, s_locations)
        result = optimizer.optimize()

        if 'routes' in result and len(result['routes']) > 0:
            route_data = result['routes'][0]
            # Enhance steps with full location objects and materials
            enhanced_steps = []
            for step in route_data['steps']:
                 # Find the location model
                 loc_name = step['location_name']
                 loc_obj = Location.objects.filter(name=loc_name).first()
                 
                 step_info = {
                     "location": LocationSerializer(loc_obj).data if loc_obj else step,
                     "type": step['type'],
                     "arrival_time_sec": step['arrival_time_sec']
                 }
                 
                 if step.get('order_id'):
                      order_obj = Order.objects.get(id=step['order_id'])
                      step_info['items'] = OrderItemSerializer(order_obj.items.all(), many=True).data
                      
                 enhanced_steps.append(step_info)

            return Response({
                "vehicle_id": vehicle.id,
                "steps": enhanced_steps,
                "distance_meters": route_data['distance_meters']
            })
        
        return Response(result)

    @action(detail=True, methods=['post'])
    def generate_route(self, request, pk=None):
        """Specifically triggers optimization for this vehicle and pending orders, assigns them."""
        vehicle = self.get_object()
        pending_orders = Order.objects.filter(status='pending')
        
        if not pending_orders.exists():
            return Response({"error": "No pending orders to assign"}, status=status.HTTP_404_NOT_FOUND)

        from .services.routing import SolverLocation, SolverOrder, SolverVehicle, RouteOptimizer
        
        locations = Location.objects.all()
        depot = vehicle.start_depot or Location.objects.filter(location_type='warehouse').first()

        s_locations = [
            SolverLocation(id=loc.id, name=loc.name, lat=loc.latitude, lng=loc.longitude, type=loc.location_type) 
            for loc in locations
        ]
        s_vehicles = [
            SolverVehicle(id=vehicle.id, start_depot_id=depot.id, end_depot_id=depot.id, 
                          capacity=vehicle.capacity, weight_capacity=vehicle.weight_capacity, max_distance=300.0)
        ]
        s_orders = [
            SolverOrder(id=o.id, from_location_id=o.assigned_warehouse.id if o.assigned_warehouse else depot.id, 
                        to_location_id=o.destination.id, volume=sum(item.quantity for item in o.items.all()), weight=o.weight) 
            for o in pending_orders
        ]

        optimizer = RouteOptimizer(s_vehicles, s_orders, s_locations)
        result = optimizer.optimize()

        if 'routes' in result and len(result['routes']) > 0:
            assigned_count = 0
            route_data = result['routes'][0]
            for step in route_data['steps']:
                if step.get('order_id') and step.get('type') == 'delivery':
                    Order.objects.filter(id=step['order_id']).update(status='assigned', assigned_vehicle=vehicle)
                    assigned_count += 1
            
            # Summary of materials to load
            assigned_order_ids = [s['order_id'] for s in route_data['steps'] if s.get('order_id') and s.get('type') == 'delivery']
            materials_sum = list(OrderItem.objects.filter(order__id__in=assigned_order_ids)
                                .values('material__name')
                                .annotate(total_qty=Sum('quantity')))
            
            return Response({
                "status": "success",
                "assigned_orders_count": assigned_count,
                "materials_to_load": materials_sum,
                "route_sequence": route_data['steps']
            })
        
        return Response({"error": "Could not generate an optimal route for this driver"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def download_route_manifest(self, request, pk=None):
        """Generates a professional driver PDF manifest."""
        vehicle = self.get_object()
        orders = Order.objects.filter(assigned_vehicle=vehicle, status='assigned')

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph(f"Driver Manifest: {vehicle.name}", styles['Title']))
        elements.append(Spacer(1, 12))

        data = [["Order ID", "Destination", "Priority", "Resources Required"]]
        for order in orders:
            items_str = ", ".join([f"{i.material.name} ({i.quantity})" for i in order.items.all()])
            data.append([f"#{order.id}", order.destination.name, order.priority.upper(), items_str])

        if not orders:
            data.append(["-", "No pending assignments", "-", "-"])

        table = Table(data, colWidths=[60, 150, 80, 200])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 1, colors.grey),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('BOTTOMPADDING', (0,0), (-1,0), 10),
        ]))
        elements.append(table)

        doc.build(elements)
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename=f"route_sheet_v{vehicle.id}.pdf")

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    filterset_fields = ['status', 'priority']
    search_fields = ['destination__name']
    ordering_fields = ['created_at', 'priority']

    @action(detail=True, methods=['post'])
    @permission_classes([AllowAny])
    @transaction.atomic
    def complete_order(self, request, pk=None):
        """Completes order and deducts material from assigned warehouse."""
        order = self.get_object()

        if order.status == 'completed':
            return Response({"error": "Order already completed"}, status=status.HTTP_400_BAD_REQUEST)

        if not order.assigned_warehouse:
            return Response({"error": "No warehouse assigned to this order"},
                            status=status.HTTP_400_BAD_REQUEST)

        # Atomic stock deduction
        for item in order.items.all():
            try:
                inv = Inventory.objects.select_for_update().get(
                    location=order.assigned_warehouse,
                    material=item.material
                )
                if inv.quantity < item.quantity:
                    raise serializers.ValidationError(
                        f"Insufficient stock for {item.material.name} at {order.assigned_warehouse.name}"
                    )
                inv.quantity -= item.quantity
                inv.save()
            except Inventory.DoesNotExist:
                raise serializers.ValidationError(f"Inventory missing for {item.material.name}")

        order.status = 'completed'
        order.save()
        return Response(self.get_serializer(order).data)

    # --- Shared Optimization Helper ---

    def _run_optimization(self, orders, time_limit=10):
        """
        Common optimization logic shared by auto_assign, reassign, and urgent_assign.
        Handles: validation, solver DTO mapping, optimization, and DB updates.
        Returns (result_dict, status_code) tuple.
        """
        from .services.routing import SolverLocation, SolverOrder, SolverVehicle, RouteOptimizer

        if not orders.exists():
            return {"routes": [], "total_distance_meters": 0, "dropped_orders": [],
                    "summary": {"total_orders": 0, "assigned_orders": 0, "dropped_orders": 0, "vehicles_used": 0}}, 200

        vehicles = Vehicle.objects.all()
        locations = Location.objects.all()
        depot = Location.objects.filter(location_type='warehouse').first()

        if not depot:
            return {"error": "No warehouse available as depot"}, 400
        if not vehicles.exists():
            return {"error": "No vehicles available"}, 400

        # Validate all orders have destinations
        valid_orders = []
        for order in orders:
            if not order.destination:
                continue
            valid_orders.append(order)

        # Auto-assign warehouses to orders based on nearest stock
        for order in valid_orders:
            if not order.assigned_warehouse and order.items.exists():
                first_item = order.items.first()
                if first_item:
                    nearest = find_nearest_warehouse(
                        order.destination.latitude,
                        order.destination.longitude,
                        first_item.material.id,
                        first_item.quantity
                    )
                    if nearest:
                        order.assigned_warehouse_id = nearest['id']
                        order.save()

        # Prefetch items for volume calculation
        orders_with_items = Order.objects.filter(
            id__in=[o.id for o in valid_orders]
        ).prefetch_related('items')
        items_by_order = {o.id: list(o.items.all()) for o in orders_with_items}

        # Map Models -> Solver Objects
        s_locations = [
            SolverLocation(
                id=loc.id, name=loc.name, lat=loc.latitude, lng=loc.longitude,
                type=loc.location_type, service_time_sec=loc.service_time_sec,
                time_window_start=loc.time_window_start, time_window_end=loc.time_window_end
            ) for loc in locations
        ]

        s_vehicles = [
            SolverVehicle(
                id=v.id, start_depot_id=v.start_depot.id if v.start_depot else depot.id,
                end_depot_id=v.end_depot.id if v.end_depot else depot.id,
                capacity=v.capacity, weight_capacity=v.weight_capacity,
                max_distance=getattr(v, 'max_distance', 100.0) or 100.0,
                cost_per_km=v.cost_per_km
            ) for v in vehicles
        ]

        s_orders = [
            SolverOrder(
                id=o.id,
                from_location_id=o.assigned_warehouse.id if o.assigned_warehouse else depot.id,
                to_location_id=o.destination.id,
                volume=sum(item.quantity for item in items_by_order.get(o.id, [])),
                weight=o.weight,
                priority=3 if o.priority == 'critical' else (2 if o.priority == 'high' else 1),
                time_window_start=o.time_window_start,
                time_window_end=o.time_window_end
            ) for o in valid_orders
        ]

        # Optimize
        optimizer = RouteOptimizer(s_vehicles, s_orders, s_locations)
        result = optimizer.optimize(time_limit=time_limit)

        if 'error' in result:
            error_type = result.get('type', 'unknown')
            status_code = 400 if error_type == 'validation_error' else 503
            return result, status_code

        # Update Statuses & Assignments
        assigned_order_ids = []
        for route_data in result.get('routes', []):
            vehicle = Vehicle.objects.filter(id=route_data['vehicle_id']).first()
            if not vehicle:
                continue
            for step in route_data['steps']:
                if step.get('order_id') and step.get('type') == 'delivery':
                    Order.objects.filter(id=step['order_id']).update(
                        status='assigned',
                        assigned_vehicle=vehicle
                    )
                    assigned_order_ids.append(step['order_id'])

        result['summary'] = {
            'total_orders': len(s_orders),
            'assigned_orders': len(assigned_order_ids),
            'dropped_orders': len(result.get('dropped_orders', [])),
            'vehicles_used': len(result.get('routes', []))
        }

        return result, 200

    @action(detail=False, methods=['post'])
    @permission_classes([AllowAny])
    @transaction.atomic
    def auto_assign(self, request):
        """
        Trigger Advanced CVRP with weight/time constraints and pickup-delivery pairs.
        Automatically assigns pending orders to vehicles.
        """
        # Prefetch related data to avoid N+1 queries
        pending_orders = Order.objects.filter(
            status='pending'
        ).select_related('destination', 'assigned_warehouse').prefetch_related('items', 'items__material')

        # Get time_limit from request with bounds (1-60 seconds)
        # Handle case where request.data might be empty or None
        try:
            time_limit = min(max(int(request.data.get('time_limit', 10)), 1), 60)
        except (TypeError, ValueError, AttributeError):
            time_limit = 10

        result, status_code = self._run_optimization(pending_orders, time_limit=time_limit)
        return Response(result, status=status_code)

    @action(detail=False, methods=['post'])
    @permission_classes([AllowAny])
    @transaction.atomic
    def reassign(self, request):
        """
        Dynamic re-routing: Recalculates routes for both pending AND assigned orders.
        Use this when orders change, vehicles become unavailable, or new urgent requests arrive.
        Supports partial re-optimization by accepting optional order_ids in request body.

        Request body (all optional):
            - order_ids (optional): List of specific order IDs to reassign
            - time_limit (optional): Solver time limit in seconds (default: 15, max: 60)
        """
        # Handle case where request.data might be empty or None
        try:
            order_ids = request.data.get('order_ids', [])
        except (TypeError, AttributeError):
            order_ids = []

        # Bound time_limit between 1 and 60 seconds
        try:
            time_limit = min(max(int(request.data.get('time_limit', 15)), 1), 60)
        except (TypeError, ValueError, AttributeError):
            time_limit = 15

        if order_ids:
            orders_to_assign = Order.objects.filter(id__in=order_ids).select_related(
                'destination', 'assigned_warehouse'
            ).prefetch_related('items', 'items__material')
            # Only reset the specific orders being reassigned
            Order.objects.filter(id__in=order_ids, status='assigned').update(
                status='pending', assigned_vehicle=None
            )
        else:
            orders_to_assign = Order.objects.filter(
                status__in=['pending', 'assigned']
            ).select_related('destination', 'assigned_warehouse').prefetch_related('items', 'items__material')
            # Reset all assigned orders
            Order.objects.filter(status='assigned').update(status='pending', assigned_vehicle=None)

        result, status_code = self._run_optimization(orders_to_assign, time_limit=time_limit)

        if status_code == 200:
            result['summary']['is_reassign'] = True

        return Response(result, status=status_code)

    @action(detail=True, methods=['post'])
    @permission_classes([AllowAny])
    @transaction.atomic
    def urgent_assign(self, request, pk=None):
        """
        Force-assign a single high-priority/urgent order into existing routes.
        Triggers automatic re-optimization including this order with maximum priority.
        """
        order = self.get_object()

        if order.status == 'completed':
            return Response({"error": "Cannot assign completed order"}, status=status.HTTP_400_BAD_REQUEST)

        # Set order to critical priority
        order.priority = 'critical'
        order.save()

        # Get all pending/assigned orders for re-optimization
        all_orders = Order.objects.filter(
            status__in=['pending', 'assigned']
        ).select_related('destination', 'assigned_warehouse').prefetch_related('items', 'items__material')

        # Reset assigned orders
        Order.objects.filter(status='assigned').update(status='pending', assigned_vehicle=None)

        # Auto-assign warehouse for urgent order if needed
        if not order.assigned_warehouse and order.items.exists():
            first_item = order.items.first()
            if first_item:
                nearest = find_nearest_warehouse(
                    order.destination.latitude,
                    order.destination.longitude,
                    first_item.material.id,
                    first_item.quantity
                )
                if nearest:
                    order.assigned_warehouse_id = nearest['id']
                    order.save()

        # Refresh orders after reset
        all_orders = Order.objects.filter(
            status__in=['pending', 'assigned']
        ).select_related('destination', 'assigned_warehouse').prefetch_related('items', 'items__material')

        result, status_code = self._run_optimization_urgent(all_orders, order.id)

        if status_code == 200:
            result['summary']['urgent_order_id'] = order.id
            result['summary']['urgent_order_assigned'] = order.id in [
                step['order_id']
                for route in result.get('routes', [])
                for step in route.get('steps', [])
                if step.get('type') == 'delivery'
            ]
            if not result['summary']['urgent_order_assigned']:
                result['warning'] = f"Urgent order #{order.id} was dropped by solver due to constraints"

        return Response(result, status=status_code)

    def _run_optimization_urgent(self, orders, urgent_order_id, time_limit=15):
        """
        Special optimization for urgent orders.
        The urgent order gets priority=3, others keep their normal priority.
        """
        from .services.routing import SolverLocation, SolverOrder, SolverVehicle, RouteOptimizer

        if not orders.exists():
            return {"routes": [], "total_distance_meters": 0, "dropped_orders": [],
                    "summary": {"total_orders": 0, "assigned_orders": 0, "dropped_orders": 0, "vehicles_used": 0}}, 200

        vehicles = Vehicle.objects.all()
        locations = Location.objects.all()
        depot = Location.objects.filter(location_type='warehouse').first()

        if not depot:
            return {"error": "No warehouse available"}, 400
        if not vehicles.exists():
            return {"error": "No vehicles available"}, 400

        # Validate all orders have destinations
        valid_orders = [o for o in orders if o.destination]

        # Prefetch items
        orders_with_items = Order.objects.filter(
            id__in=[o.id for o in valid_orders]
        ).prefetch_related('items')
        items_by_order = {o.id: list(o.items.all()) for o in orders_with_items}

        # Map Models -> Solver Objects
        s_locations = [
            SolverLocation(
                id=loc.id, name=loc.name, lat=loc.latitude, lng=loc.longitude,
                type=loc.location_type, service_time_sec=loc.service_time_sec,
                time_window_start=loc.time_window_start, time_window_end=loc.time_window_end
            ) for loc in locations
        ]

        s_vehicles = [
            SolverVehicle(
                id=v.id, start_depot_id=v.start_depot.id if v.start_depot else depot.id,
                end_depot_id=v.end_depot.id if v.end_depot else depot.id,
                capacity=v.capacity, weight_capacity=v.weight_capacity,
                max_distance=getattr(v, 'max_distance', 100.0) or 100.0,
                cost_per_km=v.cost_per_km
            ) for v in vehicles
        ]

        s_orders = [
            SolverOrder(
                id=o.id,
                from_location_id=o.assigned_warehouse.id if o.assigned_warehouse else depot.id,
                to_location_id=o.destination.id,
                volume=sum(item.quantity for item in items_by_order.get(o.id, [])),
                weight=o.weight,
                # Urgent order gets priority 3, others keep their normal priority
                priority=3 if o.id == urgent_order_id else (
                    3 if o.priority == 'critical' else (2 if o.priority == 'high' else 1)
                ),
                time_window_start=o.time_window_start,
                time_window_end=o.time_window_end
            ) for o in valid_orders
        ]

        optimizer = RouteOptimizer(s_vehicles, s_orders, s_locations)
        result = optimizer.optimize(time_limit=time_limit)

        if 'error' in result:
            error_type = result.get('type', 'unknown')
            status_code = 400 if error_type == 'validation_error' else 503
            return result, status_code

        # Update Statuses & Assignments
        assigned_order_ids = []
        for route_data in result.get('routes', []):
            vehicle = Vehicle.objects.filter(id=route_data['vehicle_id']).first()
            if not vehicle:
                continue
            for step in route_data['steps']:
                if step.get('order_id') and step.get('type') == 'delivery':
                    Order.objects.filter(id=step['order_id']).update(
                        status='assigned',
                        assigned_vehicle=vehicle
                    )
                    assigned_order_ids.append(step['order_id'])

        result['summary'] = {
            'total_orders': len(s_orders),
            'assigned_orders': len(assigned_order_ids),
            'dropped_orders': len(result.get('dropped_orders', [])),
            'vehicles_used': len(result.get('routes', []))
        }

        return result, 200

class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer

class AnalyticsView(views.APIView):
    def get(self, request):
        """Returns complex KPIs for the logistics dashboard."""
        warehouses = Location.objects.filter(location_type='warehouse')
        stock_summary = []
        for w in warehouses:
            total_items = Inventory.objects.filter(location=w).aggregate(total=Sum('quantity'))['total'] or 0
            stock_summary.append({"name": w.name, "total_stock": total_items})

        data = {
            "active_orders_count": Order.objects.exclude(status='completed').count(),
            "critical_orders_count": Order.objects.filter(priority='critical').exclude(status='completed').count(),
            "total_vehicles_online": Vehicle.objects.filter(is_online=True).count(),
            "warehouse_stock_summary": stock_summary,
            "low_stock_alerts": Inventory.objects.filter(quantity__lt=10).count()
        }
        return Response(data)
