# tests/test_routes.py
from app import main  # Import your Flask app

def test_homepage_loads():
    """Test that the homepage returns a 200 OK status."""
    # Create a test client that simulates a web browser
    tester = app.test_client()
    
    # Simulate a GET request to the root URL
    response = tester.get('/')
    
    # Assert that the server responded with a success code (200)
    assert response.status_code == 200
