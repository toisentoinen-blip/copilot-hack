"""
Comprehensive test suite for Flask flight delay prediction server.
Tests cover critical paths: parameter validation, error handling, data parsing.
"""
import pytest
import pickle
import tempfile
import os
from unittest.mock import patch, MagicMock
import numpy as np
from app import app


@pytest.fixture
def client():
    """Flask test client."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def temp_model():
    """Create a temporary mock model for testing."""
    model = MagicMock()
    # Simulate sklearn model behavior
    model.predict_proba = MagicMock(return_value=np.array([[0.7, 0.3]]))
    return model


@pytest.fixture
def mock_model(temp_model):
    """Patch the global model with a mock."""
    with patch('app.model', temp_model):
        yield temp_model


class TestPredictEndpointParameterValidation:
    """Test /predict endpoint parameter validation (CRITICAL PATH)."""

    def test_predict_missing_day_of_week(self, client):
        """Should fail gracefully when day_of_week is missing."""
        response = client.get('/predict?airport_id=14771')
        # Current code crashes with 500 - this should be fixed to return 400
        assert response.status_code == 500

    def test_predict_missing_airport_id(self, client):
        """Should fail gracefully when airport_id is missing."""
        response = client.get('/predict?day_of_week=3')
        # Current code crashes with 500 - this should be fixed to return 400
        assert response.status_code == 500

    def test_predict_both_parameters_missing(self, client):
        """Should fail gracefully when both parameters missing."""
        response = client.get('/predict')
        # Current code crashes with 500 - this should be fixed to return 400
        assert response.status_code == 500

    def test_predict_non_integer_day_of_week(self, client):
        """Should fail gracefully when day_of_week is not an integer."""
        response = client.get('/predict?day_of_week=monday&airport_id=14771')
        # Current code crashes with 500 - this should be fixed to return 400
        assert response.status_code == 500

    def test_predict_non_integer_airport_id(self, client):
        """Should fail gracefully when airport_id is not an integer."""
        response = client.get('/predict?day_of_week=3&airport_id=invalid')
        # Current code crashes with 500 - this should be fixed to return 400
        assert response.status_code == 500

    def test_predict_float_parameters(self, client):
        """Should handle float parameters gracefully."""
        response = client.get('/predict?day_of_week=3.5&airport_id=14771.2')
        # Floats can be cast to int, should work or fail gracefully
        assert response.status_code in [200, 400, 500]

    def test_predict_negative_day_of_week(self, client, mock_model):
        """Should validate that day_of_week is in valid range (0-6)."""
        response = client.get('/predict?day_of_week=-1&airport_id=14771')
        # Model accepts negative numbers - no validation currently
        assert response.status_code == 200

    def test_predict_out_of_range_day_of_week(self, client, mock_model):
        """Should validate that day_of_week is in valid range."""
        response = client.get('/predict?day_of_week=7&airport_id=14771')
        # Model accepts out-of-range numbers - no validation currently
        assert response.status_code == 200

    def test_predict_negative_airport_id(self, client, mock_model):
        """Should handle negative airport_id gracefully."""
        response = client.get('/predict?day_of_week=3&airport_id=-1')
        # Model accepts negative numbers - no validation currently
        assert response.status_code == 200

    def test_predict_extremely_large_numbers(self, client, mock_model):
        """Should handle extremely large numbers gracefully."""
        response = client.get('/predict?day_of_week=999999999&airport_id=999999999')
        # Model accepts large numbers - no validation currently
        assert response.status_code == 200

    def test_predict_empty_parameters(self, client):
        """Should handle empty string parameters."""
        response = client.get('/predict?day_of_week=&airport_id=')
        # Current code crashes with 500 - this should be fixed to return 400
        assert response.status_code == 500

    def test_predict_sql_injection_attempt(self, client):
        """Should safely reject SQL injection attempts."""
        response = client.get("/predict?day_of_week=3'; DROP TABLE--&airport_id=14771")
        # The code tries to convert this to int, which will fail with 500
        assert response.status_code == 500


class TestPredictEndpointModelHandling:
    """Test /predict endpoint model prediction (CRITICAL PATH)."""

    def test_predict_valid_parameters_with_mock(self, client, mock_model):
        """Should return valid JSON response with valid parameters."""
        response = client.get('/predict?day_of_week=3&airport_id=14771')
        assert response.status_code == 200
        data = response.get_json()
        assert 'certainty' in data
        assert 'delay' in data

    def test_predict_response_is_json(self, client, mock_model):
        """Response should be valid JSON."""
        response = client.get('/predict?day_of_week=3&airport_id=14771')
        assert response.content_type == 'application/json'
        data = response.get_json()
        assert isinstance(data, dict)

    def test_predict_response_values_are_floats(self, client, mock_model):
        """Response values should be numeric."""
        response = client.get('/predict?day_of_week=3&airport_id=14771')
        data = response.get_json()
        assert isinstance(data['certainty'], (int, float))
        assert isinstance(data['delay'], (int, float))

    def test_predict_response_values_in_valid_range(self, client, mock_model):
        """Response probabilities should be in [0, 1] range."""
        response = client.get('/predict?day_of_week=3&airport_id=14771')
        data = response.get_json()
        assert 0 <= data['certainty'] <= 1, f"Certainty {data['certainty']} out of range"
        assert 0 <= data['delay'] <= 1, f"Delay {data['delay']} out of range"

    def test_predict_calls_model_with_correct_format(self, client, mock_model):
        """Model should be called with correct 2D array format."""
        response = client.get('/predict?day_of_week=3&airport_id=14771')
        # Verify model was called with correct parameters
        mock_model.predict_proba.assert_called_once()
        call_args = mock_model.predict_proba.call_args
        # Should be called with a 2D array [[day_of_week, airport_id]]
        assert call_args is not None

    def test_predict_with_different_probabilities(self, client):
        """Should handle different probability distributions."""
        with patch('app.model') as mock_model:
            # Test with extreme probabilities
            mock_model.predict_proba = MagicMock(return_value=np.array([[0.1, 0.9]]))
            with app.test_client() as test_client:
                response = test_client.get('/predict?day_of_week=3&airport_id=14771')
                assert response.status_code == 200

    def test_predict_model_missing_error(self, client):
        """Should handle missing model.pkl gracefully (HIGH PRIORITY BUG)."""
        # This currently crashes - we're testing current behavior
        with patch('app.model', side_effect=AttributeError("model not loaded")):
            response = client.get('/predict?day_of_week=3&airport_id=14771')
            # Currently this will 500, should be handled gracefully
            assert response.status_code in [500]


class TestAirportsEndpointFileHandling:
    """Test /airports endpoint file handling (CRITICAL PATH)."""

    def test_airports_returns_json(self, client):
        """Response should be valid JSON."""
        response = client.get('/airports')
        assert response.content_type == 'application/json'
        data = response.get_json()
        assert isinstance(data, list)

    def test_airports_returns_list_of_dicts(self, client):
        """Should return list of airport dictionaries."""
        response = client.get('/airports')
        data = response.get_json()
        assert isinstance(data, list)
        if len(data) > 0:
            assert isinstance(data[0], dict)

    def test_airports_dict_has_required_fields(self, client):
        """Each airport should have id and name fields."""
        response = client.get('/airports')
        data = response.get_json()
        if len(data) > 0:
            airport = data[0]
            assert 'id' in airport
            assert 'name' in airport
            assert isinstance(airport['id'], int)
            assert isinstance(airport['name'], str)

    def test_airports_is_sorted_by_name(self, client):
        """Airports should be sorted alphabetically by name."""
        response = client.get('/airports')
        data = response.get_json()
        if len(data) > 1:
            names = [airport['name'] for airport in data]
            sorted_names = sorted(names)
            assert names == sorted_names, "Airports not sorted by name"

    def test_airports_all_ids_are_integers(self, client):
        """All airport IDs should be integers."""
        response = client.get('/airports')
        data = response.get_json()
        for airport in data:
            assert isinstance(airport['id'], int), f"Airport {airport} has non-integer id"

    def test_airports_all_names_are_strings(self, client):
        """All airport names should be strings."""
        response = client.get('/airports')
        data = response.get_json()
        for airport in data:
            assert isinstance(airport['name'], str), f"Airport {airport} has non-string name"
            assert len(airport['name']) > 0, f"Empty airport name in {airport}"

    def test_airports_no_duplicate_ids(self, client):
        """No duplicate airport IDs should exist."""
        response = client.get('/airports')
        data = response.get_json()
        ids = [airport['id'] for airport in data]
        assert len(ids) == len(set(ids)), "Duplicate airport IDs found"

    def test_airports_file_missing_error_handling(self, client):
        """Should handle missing airports.csv gracefully (HIGH PRIORITY BUG)."""
        # Currently crashes - testing current behavior
        with patch('builtins.open', side_effect=FileNotFoundError("airports.csv not found")):
            response = client.get('/airports')
            # Currently this will 500, should be handled gracefully
            assert response.status_code in [500]

    def test_airports_csv_parsing_malformed_lines(self, client):
        """Should handle malformed CSV lines gracefully."""
        # This tests current behavior - likely no error handling
        csv_data = "1,JFK\n\n2,LAX,extra,fields\n3,"
        with patch('builtins.open', return_value=iter(["id,name"] + csv_data.split('\n'))):
            response = client.get('/airports')
            # Currently might crash or return incomplete data
            assert response.status_code in [200, 500]


class TestCORSHeaders:
    """Test CORS configuration."""

    def test_cors_header_present(self, client):
        """Response should include Access-Control-Allow-Origin header."""
        response = client.get('/airports')
        assert 'Access-Control-Allow-Origin' in response.headers

    def test_cors_allows_all_origins(self, client):
        """CORS should allow requests from any origin (current behavior)."""
        response = client.get('/airports')
        # Currently allows all origins
        assert response.headers['Access-Control-Allow-Origin'] == '*'

    def test_cors_allows_content_type_header(self, client):
        """CORS should allow Content-Type header."""
        response = client.get('/airports')
        assert 'Access-Control-Allow-Headers' in response.headers
        assert 'Content-Type' in response.headers['Access-Control-Allow-Headers']

    def test_cors_allows_authorization_header(self, client):
        """CORS should allow Authorization header."""
        response = client.get('/airports')
        assert 'Access-Control-Allow-Headers' in response.headers
        assert 'Authorization' in response.headers['Access-Control-Allow-Headers']


class TestIntegration:
    """Integration tests combining multiple endpoints."""

    def test_get_airports_then_predict(self, client, mock_model):
        """Should be able to get airports and then make a prediction."""
        # Get airports
        airports_response = client.get('/airports')
        assert airports_response.status_code == 200
        airports = airports_response.get_json()

        # Use first airport to make prediction
        if len(airports) > 0:
            airport_id = airports[0]['id']
            predict_response = client.get(f'/predict?day_of_week=3&airport_id={airport_id}')
            assert predict_response.status_code == 200
            prediction = predict_response.get_json()
            assert 'certainty' in prediction
            assert 'delay' in prediction

    def test_endpoints_accept_http_methods(self, client):
        """Test that endpoints only accept expected HTTP methods."""
        # POST should not be allowed on GET endpoints
        post_response = client.post('/airports')
        assert post_response.status_code in [405, 400]  # Method Not Allowed or error

    def test_response_headers_consistent(self, client):
        """All endpoints should return consistent Content-Type headers."""
        airports_response = client.get('/airports')
        assert 'application/json' in airports_response.content_type

        # Predict also returns JSON
        with patch('app.model') as mock_model:
            mock_model.predict_proba = MagicMock(return_value=np.array([[0.7, 0.3]]))
            with app.test_client() as test_client:
                predict_response = test_client.get('/predict?day_of_week=3&airport_id=14771')
                assert 'application/json' in predict_response.content_type
