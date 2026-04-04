import io
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import FileResponse
from rest_framework import viewsets, status, views, serializers
from rest_framework.decorators import action
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

    @transaction.atomic
    @action(detail=True, methods=['post'])
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

    @action(detail=False, methods=['post'])
    def auto_assign(self, request):
        """Trigger CVRP and update order statuses with vehicle/warehouse assignments."""
        pending_orders = Order.objects.filter(status='pending')
        vehicles = Vehicle.objects.all()
        depot = Location.objects.filter(location_type='warehouse').first()

        if not depot:
            return Response({"error": "No warehouse available"}, status=status.HTTP_400_BAD_REQUEST)

        optimizer = RouteOptimizer(list(vehicles), list(pending_orders), depot)
        result = optimizer.optimize()

        if 'error' in result:
             return Response(result, status=status.HTTP_400_BAD_REQUEST)

        for route in result.get('routes', []):
            vehicle = Vehicle.objects.get(id=route['vehicle_id'])
            for step in route['steps']:
                if step['order_id']:
                     Order.objects.filter(id=step['order_id']).update(
                         status='assigned',
                         assigned_warehouse=depot,
                         assigned_vehicle=vehicle
                     )

        return Response(result)

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
