import numpy as np
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from geopy.distance import geodesic
from ..models import Location, Vehicle, Order

class RouteOptimizer:
    def __init__(self, vehicles, orders, depot_location):
        self.vehicles = vehicles
        self.orders = orders
        self.depot = depot_location
        # Depot is the first location
        self.locations = [depot_location] + [order.destination for order in orders]
        self.num_vehicles = len(vehicles)
        self.depot_index = 0

    def _create_distance_matrix(self):
        size = len(self.locations)
        matrix = np.zeros((size, size))
        for i in range(size):
            for j in range(size):
                if i == j:
                    matrix[i][j] = 0
                else:
                    loc1 = (self.locations[i].latitude, self.locations[i].longitude)
                    loc2 = (self.locations[j].latitude, self.locations[j].longitude)
                    # Use meters for integer precision required by OR-Tools
                    matrix[i][j] = int(geodesic(loc1, loc2).meters)
        return matrix.tolist()

    def optimize(self):
        if not self.orders or not self.vehicles:
            return {"error": "No orders or vehicles provided"}

        data = {}
        data['distance_matrix'] = self._create_distance_matrix()
        # Demand is the sum of items in each order. Depot has 0 demand.
        data['demands'] = [0] + [sum(item.quantity for item in order.items.all()) for order in self.orders]
        data['vehicle_capacities'] = [int(v.capacity) for v in self.vehicles]
        data['num_vehicles'] = len(self.vehicles)
        data['depot'] = self.depot_index

        # Add penalties for prioritizing critical orders
        # Penalty = huge for critical, large for high, medium for normal
        penalty_vals = {'critical': 1000000, 'high': 100000, 'normal': 10000}
        data['penalties'] = [penalty_vals.get(order.priority, 10000) for order in self.orders]

        manager = pywrapcp.RoutingIndexManager(len(data['distance_matrix']),
                                              data['num_vehicles'], data['depot'])
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return data['distance_matrix'][from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        def demand_callback(from_index):
            from_node = manager.IndexToNode(from_index)
            return data['demands'][from_node]

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,  # null capacity slack
            data['vehicle_capacities'],  # vehicle maximum capacities
            True,  # start cumul to zero
            'Capacity')

        # Add disjunctions (penalties for missing orders)
        # We match node index (1 to N) with penalty index (0 to N-1)
        for i in range(1, len(data['distance_matrix'])):
            routing.AddDisjunction([manager.NodeToIndex(i)], data['penalties'][i-1])

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        search_parameters.time_limit.seconds = 10

        solution = routing.SolveWithParameters(search_parameters)

        if solution:
            return self._format_solution(data, manager, routing, solution)
        else:
            return {"error": "No solution found"}

    def _format_solution(self, data, manager, routing, solution):
        result = {"routes": []}
        total_distance = 0
        total_load = 0
        
        for vehicle_id in range(data['num_vehicles']):
            index = routing.Start(vehicle_id)
            route = {
                "vehicle_id": self.vehicles[vehicle_id].id,
                "vehicle_name": self.vehicles[vehicle_id].name,
                "steps": [],
                "route_coordinates": [], # [[lat, lng], [lat, lng]...]
                "distance_meters": 0,
                "load": 0
            }
            route_distance = 0
            route_load = 0
            
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                route_load += data['demands'][node_index]
                loc = self.locations[node_index]
                
                step_type = "pickup" if node_index == 0 else "delivery"
                
                route['steps'].append({
                    "type": step_type,
                    "location_name": loc.name,
                    "coords": [loc.latitude, loc.longitude],
                    "order_id": self.orders[node_index-1].id if node_index > 0 else None,
                    "priority": self.orders[node_index-1].priority if node_index > 0 else None
                })
                
                route['route_coordinates'].append([loc.latitude, loc.longitude])
                
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                route_distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)

            # Add final depot return
            node_index = manager.IndexToNode(index)
            loc = self.locations[node_index]
            route['steps'].append({
                "type": "return",
                "location_name": loc.name,
                "coords": [loc.latitude, loc.longitude],
                "order_id": None,
                "priority": None
            })
            route['route_coordinates'].append([loc.latitude, loc.longitude])
            
            route['distance_meters'] = route_distance
            route['load'] = route_load
            result['routes'].append(route)
            
            total_distance += route_distance
            total_load += route_load

        result['total_distance_meters'] = total_distance
        result['total_load'] = total_load
        
        # Track dropped orders
        dropped_orders = []
        for node in range(1, len(data['distance_matrix'])):
            if solution.Value(routing.NextVar(manager.NodeToIndex(node))) == manager.NodeToIndex(node):
                dropped_orders.append({
                    "order_id": self.orders[node-1].id,
                    "priority": self.orders[node-1].priority
                })
        result['dropped_orders'] = dropped_orders

        return result
