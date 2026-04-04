import requests
import json

BASE_URL = "http://127.0.0.1:8000/api"

def test_auto_assign():
    print("Testing Advanced auto_assign (CVRP + Pickups + Weight + Time)...")
    try:
        response = requests.post(f"{BASE_URL}/orders/auto_assign/")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(json.dumps(data, indent=2))
            
            # Check for routes and steps
            routes = data.get('routes', [])
            print(f"\nGenerated {len(routes)} routes.")
            for r in routes:
                print(f"Vehicle {r['vehicle_id']} has {len(r['steps'])} steps.")
        else:
            print(response.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_auto_assign()
