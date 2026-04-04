from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import time
import math
from typing import List, Optional
from dataclasses import dataclass, field
from django.conf import settings

# --- Data Models (Internal for the solver) ---

class NodeType:
    DEPOT = "warehouse"
    SUPPLIER = "supplier"
    DELIVERY_POINT = "customer"
    HOTSPOT = "hotspot"

@dataclass
class SolverLocation:
    id: int
    name: str
    lat: float
    lng: float
    type: str
    service_time_sec: float = 0.0
    time_window_start: Optional[float] = None
    time_window_end: Optional[float] = None

@dataclass
class SolverOrder:
    id: int
    from_location_id: int  # Pickup
    to_location_id: int    # Delivery
    volume: float
    weight: float = 0.0
    priority: int = 1
    time_window_start: Optional[float] = None
    time_window_end: Optional[float] = None

@dataclass
class SolverVehicle:
    id: int
    start_depot_id: int
    end_depot_id: int
    capacity: float
    weight_capacity: float
    max_distance: float
    cost_per_km: float = 1.0

# --- The Optimizer Engine ---

class RouteOptimizer:
    def __init__(self, vehicles, orders, locations):
        self.vehicles = vehicles
        self.orders = orders
        self.locations = locations
        
        # Map location ID -> index for OR-Tools
        self.id_to_idx = {loc.id: i for i, loc in enumerate(locations)}
        
    def _haversine(self, lat1, lon1, lat2, lon2):
        R = 6371.0  # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * \
            math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def optimize(self, time_limit=10):
        # 1. Setup Data
        num_locations = len(self.locations)
        num_vehicles = len(self.vehicles)
        
        starts = [self.id_to_idx[v.start_depot_id] for v in self.vehicles]
        ends = [self.id_to_idx[v.end_depot_id] for v in self.vehicles]
        
        manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, starts, ends)
        routing = pywrapcp.RoutingModel(manager)

        # 2. Distance Matrix & Cost
        def distance_callback(from_idx, to_idx):
            from_node = manager.IndexToNode(from_idx)
            to_node = manager.IndexToNode(to_idx)
            loc1 = self.locations[from_node]
            loc2 = self.locations[to_node]
            dist = self._haversine(loc1.lat, loc1.lng, loc2.lat, loc2.lng)
            return int(dist * 1000)  # In meters

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # 3. Pickup and Delivery
        for order in self.orders:
            pickup_idx = manager.NodeToIndex(self.id_to_idx[order.from_location_id])
            delivery_idx = manager.NodeToIndex(self.id_to_idx[order.to_location_id])
            routing.AddPickupAndDelivery(pickup_idx, delivery_idx)
            routing.solver().Add(routing.VehicleVar(pickup_idx) == routing.VehicleVar(delivery_idx))
            
            # Sequence: Pickup before delivery
            # (Actually OR-Tools does this automatically with AddPickupAndDelivery, 
            # but we can enforce it strictly if needed via dimensions)

        # 4. Dimensions (Capacity, Weight, Distance, Time)
        
        # 4.1 Volume (Capacity)
        demands = [0] * num_locations
        for order in self.orders:
            demands[self.id_to_idx[order.from_location_id]] += order.volume
            demands[self.id_to_idx[order.to_location_id]] -= order.volume

        def demand_callback(from_idx):
            return int(demands[manager.IndexToNode(from_idx)] * 100)
            
        demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_idx, 0, [int(v.capacity * 100) for v in self.vehicles], True, "Capacity"
        )

        # 4.2 Weight
        weights = [0] * num_locations
        for order in self.orders:
            weights[self.id_to_idx[order.from_location_id]] += order.weight
            weights[self.id_to_idx[order.to_location_id]] -= order.weight

        def weight_callback(from_idx):
            return int(weights[manager.IndexToNode(from_idx)] * 100)
            
        weight_idx = routing.RegisterUnaryTransitCallback(weight_callback)
        routing.AddDimensionWithVehicleCapacity(
            weight_idx, 0, [int(v.weight_capacity * 100) for v in self.vehicles], True, "Weight"
        )

        # 4.3 Distance (Max range)
        routing.AddDimension(transit_callback_index, 0, 10000000, True, "Distance")
        distance_dim = routing.GetDimensionOrDie("Distance")
        for i, v in enumerate(self.vehicles):
            distance_dim.CumulVar(routing.End(i)).SetMax(int(v.max_distance * 1000))

        # 4.4 Time Windows
        def time_callback(from_idx, to_idx):
            f_node = manager.IndexToNode(from_idx)
            t_node = manager.IndexToNode(to_idx)
            l1, l2 = self.locations[f_node], self.locations[t_node]
            # Assumed speed 50 km/h = 13.8 m/s
            dist_m = self._haversine(l1.lat, l1.lng, l2.lat, l2.lng) * 1000
            travel_sec = dist_m / 13.88
            return int(travel_sec + l1.service_time_sec)

        time_idx = routing.RegisterTransitCallback(time_callback)
        routing.AddDimension(time_idx, 86400, 86400 * 7, False, "Time")
        time_dim = routing.GetDimensionOrDie("Time")
        
        # Set time windows for locations
        for i, loc in enumerate(self.locations):
            if loc.time_window_start is not None or loc.time_window_end is not None:
                start = int(loc.time_window_start or 0)
                end = int(loc.time_window_end or 86400 * 7)
                time_dim.CumulVar(manager.NodeToIndex(i)).SetRange(start, end)
        
        # Set time windows for order deliveries
        for order in self.orders:
            if order.time_window_start is not None or order.time_window_end is not None:
                d_idx = manager.NodeToIndex(self.id_to_idx[order.to_location_id])
                start = int(order.time_window_start or 0)
                end = int(order.time_window_end or 86400 * 7)
                time_dim.CumulVar(d_idx).SetRange(start, end)

        # 5. Disjunctions (Dropped orders with penalty)
        for order in self.orders:
            p_idx = manager.NodeToIndex(self.id_to_idx[order.from_location_id])
            d_idx = manager.NodeToIndex(self.id_to_idx[order.to_location_id])
            penalty = order.priority * 1000000
            if p_idx != -1: routing.AddDisjunction([p_idx], penalty)
            if d_idx != -1: routing.AddDisjunction([d_idx], penalty)

        # 6. Solve
        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        params.time_limit.FromSeconds(time_limit)
        
        solution = routing.SolveWithParameters(params)
        if solution:
            return self._format_solution(manager, routing, solution)
        return {"error": "No solution found"}

    def _format_solution(self, manager, routing, solution):
        result = {"routes": [], "total_distance_meters": 0}
        total_dist = 0
        
        time_dim = routing.GetDimensionOrDie("Time")
        dist_dim = routing.GetDimensionOrDie("Distance")

        for v_idx, vehicle in enumerate(self.vehicles):
            index = routing.Start(v_idx)
            route = {
                "vehicle_id": vehicle.id,
                "steps": [],
                "route_coordinates": [],
                "distance_meters": 0
            }
            
            while not routing.IsEnd(index):
                node_idx = manager.IndexToNode(index)
                loc = self.locations[node_idx]
                
                # Identify if this is a pickup or delivery
                o_id = None
                s_type = "depot"
                if loc.type == NodeType.SUPPLIER: s_type = "pickup"
                elif loc.type == NodeType.DELIVERY_POINT: s_type = "delivery"
                
                for o in self.orders:
                    if s_type == "pickup" and o.from_location_id == loc.id: o_id = o.id
                    if s_type == "delivery" and o.to_location_id == loc.id: o_id = o.id

                route['steps'].append({
                    "type": s_type,
                    "location_name": loc.name,
                    "coords": [loc.lat, loc.lng],
                    "order_id": o_id,
                    "arrival_time_sec": solution.Value(time_dim.CumulVar(index))
                })
                route['route_coordinates'].append([loc.lat, loc.lng])
                index = solution.Value(routing.NextVar(index))

            # Final depot
            node_idx = manager.IndexToNode(index)
            loc = self.locations[node_idx]
            final_dist = solution.Value(dist_dim.CumulVar(index))
            total_dist += final_dist
            
            route['steps'].append({
                "type": "return",
                "location_name": loc.name,
                "coords": [loc.lat, loc.lng],
                "order_id": None,
                "arrival_time_sec": solution.Value(time_dim.CumulVar(index))
            })
            route['route_coordinates'].append([loc.lat, loc.lng])
            route['distance_meters'] = final_dist
            result['routes'].append(route)

        result['total_distance_meters'] = total_dist
        
        # Dropped orders
        dropped = []
        for o in self.orders:
            p_idx = manager.NodeToIndex(self.id_to_idx[o.from_location_id])
            if solution.Value(routing.NextVar(p_idx)) == p_idx:
                dropped.append(o.id)
        result['dropped_orders'] = dropped
        
        return result
