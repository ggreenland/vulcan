"""Tests for API endpoints."""

import pytest
import pytest_asyncio
import os
import tempfile
from unittest.mock import AsyncMock, patch

# Set test environment before imports
os.environ['DEV_MODE'] = 'true'
os.environ['ENABLE_API_KEYS'] = 'true'
os.environ['DATABASE_PATH'] = ':memory:'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['GOOGLE_CLIENT_ID'] = 'test-client-id'
os.environ['GOOGLE_CLIENT_SECRET'] = 'test-secret'
os.environ['ALLOWED_EMAILS'] = 'test@example.com'
os.environ['BASE_URL'] = 'http://localhost:8000'

from fastapi.testclient import TestClient
from app.main import app
from app.fireplace import FireplaceStatus
from app import database


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_fireplace_status():
    """Create a mock fireplace status."""
    return FireplaceStatus(
        power=True,
        flame_level=50,
        burner2=True,
        pilot=True,
        raw_response='0303000000035c8a82c900040000011f00c8'
    )


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_returns_ok(self, client):
        response = client.get('/health')
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ok'
        assert 'dev_mode' in data


class TestTestEndpoints:
    """Test the /test/* endpoints (no auth required)."""

    def test_test_status_success(self, client, mock_fireplace_status):
        with patch('app.main.fireplace.get_status', new_callable=AsyncMock) as mock:
            mock.return_value = mock_fireplace_status

            response = client.get('/test/status')

            assert response.status_code == 200
            data = response.json()
            assert data['power'] is True
            assert data['flame_level'] == 50
            assert data['burner2'] is True
            assert data['pilot'] is True

    def test_test_status_connection_error(self, client):
        with patch('app.main.fireplace.get_status', new_callable=AsyncMock) as mock:
            mock.side_effect = ConnectionError('Failed to connect')

            response = client.get('/test/status')

            assert response.status_code == 503

    def test_test_flame_valid(self, client):
        with patch('app.main.fireplace.set_flame_level', new_callable=AsyncMock) as mock:
            mock.return_value = True

            response = client.post('/test/flame/50')

            assert response.status_code == 200
            assert response.json()['flame_level'] == 50
            mock.assert_called_once_with(50)

    def test_test_flame_invalid_low(self, client):
        response = client.post('/test/flame/-1')
        assert response.status_code == 400

    def test_test_flame_invalid_high(self, client):
        response = client.post('/test/flame/101')
        assert response.status_code == 400

    def test_test_burner2_on(self, client):
        with patch('app.main.fireplace.burner2_on', new_callable=AsyncMock) as mock:
            mock.return_value = True

            response = client.post('/test/burner2/on')

            assert response.status_code == 200
            assert response.json()['burner2'] == 'on'

    def test_test_burner2_off(self, client):
        with patch('app.main.fireplace.burner2_off', new_callable=AsyncMock) as mock:
            mock.return_value = True

            response = client.post('/test/burner2/off')

            assert response.status_code == 200
            assert response.json()['burner2'] == 'off'

    def test_test_burner2_invalid(self, client):
        response = client.post('/test/burner2/invalid')
        assert response.status_code == 400


class TestProtectedEndpoints:
    """Test that protected endpoints require authentication."""

    def test_api_status_requires_auth(self, client):
        response = client.get('/api/status')
        assert response.status_code == 401

    def test_api_power_on_requires_auth(self, client):
        response = client.post('/api/power/on')
        assert response.status_code == 401

    def test_api_power_off_requires_auth(self, client):
        response = client.post('/api/power/off')
        assert response.status_code == 401

    def test_api_flame_requires_auth(self, client):
        response = client.post('/api/flame/50')
        assert response.status_code == 401

    def test_api_burner2_on_requires_auth(self, client):
        response = client.post('/api/burner2/on')
        assert response.status_code == 401

    def test_api_keys_requires_auth(self, client):
        response = client.get('/api/keys')
        assert response.status_code == 401


class TestAuthFlow:
    """Test authentication flow."""

    def test_login_redirects_to_google(self, client):
        response = client.get('/auth/login', follow_redirects=False)

        assert response.status_code == 307
        location = response.headers['location']
        assert 'accounts.google.com' in location
        assert 'client_id=test-client-id' in location

    def test_callback_without_code_fails(self, client):
        response = client.get('/auth/callback', follow_redirects=False)

        assert response.status_code == 307
        assert 'error=missing_params' in response.headers['location']

    def test_callback_with_invalid_state_fails(self, client):
        response = client.get(
            '/auth/callback?code=test&state=invalid',
            follow_redirects=False
        )

        assert response.status_code == 307
        assert 'error=invalid_state' in response.headers['location']


class TestWebUI:
    """Test web UI endpoint."""

    def test_index_renders(self, client):
        response = client.get('/')

        assert response.status_code == 200
        assert 'Vulcan' in response.text

    def test_index_shows_login_when_not_authenticated(self, client):
        response = client.get('/')

        assert response.status_code == 200
        assert 'Sign in with Google' in response.text

    def test_static_css_served(self, client):
        response = client.get('/static/style.css')
        assert response.status_code == 200
        assert 'text/css' in response.headers['content-type']

    def test_static_js_served(self, client):
        response = client.get('/static/app.js')
        assert response.status_code == 200
        assert 'javascript' in response.headers['content-type']
