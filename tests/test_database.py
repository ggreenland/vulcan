"""Tests for database operations."""

import pytest
import pytest_asyncio
import os
import tempfile

# Override database path before importing
os.environ['DATABASE_PATH'] = ':memory:'

from app import database


@pytest_asyncio.fixture
async def db():
    """Initialize a fresh in-memory database for each test."""
    # Use a temporary file for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        test_db_path = f.name

    # Monkey-patch the database path
    original_path = database.DATABASE_PATH
    database.DATABASE_PATH = test_db_path

    await database.init_db()
    yield

    # Cleanup
    database.DATABASE_PATH = original_path
    os.unlink(test_db_path)


@pytest.mark.asyncio
async def test_init_db_creates_tables(db):
    """Test that init_db creates required tables."""
    import aiosqlite

    async with aiosqlite.connect(database.DATABASE_PATH) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in await cursor.fetchall()}

    assert 'users' in tables
    assert 'sessions' in tables
    assert 'api_keys' in tables


@pytest.mark.asyncio
async def test_create_user(db):
    """Test creating a new user."""
    user = await database.get_or_create_user(
        email='test@example.com',
        name='Test User',
        picture='https://example.com/pic.jpg'
    )

    assert user['email'] == 'test@example.com'
    assert user['name'] == 'Test User'
    assert user['picture'] == 'https://example.com/pic.jpg'
    assert user['id'] is not None


@pytest.mark.asyncio
async def test_get_existing_user(db):
    """Test that getting an existing user returns the same user."""
    user1 = await database.get_or_create_user(
        email='test@example.com',
        name='Test User',
        picture='https://example.com/pic.jpg'
    )

    user2 = await database.get_or_create_user(
        email='test@example.com',
        name='Updated Name',
        picture='https://example.com/new.jpg'
    )

    assert user1['id'] == user2['id']


@pytest.mark.asyncio
async def test_create_session(db):
    """Test creating a session for a user."""
    user = await database.get_or_create_user(
        email='test@example.com',
        name='Test',
        picture=''
    )

    session_id = await database.create_session(user['id'])

    assert session_id is not None
    assert len(session_id) > 20  # Should be a long random string


@pytest.mark.asyncio
async def test_get_valid_session(db):
    """Test retrieving a valid session."""
    user = await database.get_or_create_user(
        email='test@example.com',
        name='Test',
        picture=''
    )
    session_id = await database.create_session(user['id'])

    session = await database.get_session(session_id)

    assert session is not None
    assert session['email'] == 'test@example.com'
    assert session['user_id'] == user['id']


@pytest.mark.asyncio
async def test_get_invalid_session(db):
    """Test that invalid session returns None."""
    session = await database.get_session('invalid-session-id')
    assert session is None


@pytest.mark.asyncio
async def test_delete_session(db):
    """Test deleting a session."""
    user = await database.get_or_create_user(
        email='test@example.com',
        name='Test',
        picture=''
    )
    session_id = await database.create_session(user['id'])

    await database.delete_session(session_id)

    session = await database.get_session(session_id)
    assert session is None


@pytest.mark.asyncio
async def test_create_api_key(db):
    """Test creating an API key."""
    user = await database.get_or_create_user(
        email='test@example.com',
        name='Test',
        picture=''
    )

    key_id, raw_key = await database.create_api_key(user['id'], 'Test Key')

    assert key_id is not None
    assert raw_key is not None
    assert len(raw_key) > 20


@pytest.mark.asyncio
async def test_validate_api_key(db):
    """Test validating an API key."""
    user = await database.get_or_create_user(
        email='test@example.com',
        name='Test',
        picture=''
    )
    key_id, raw_key = await database.create_api_key(user['id'], 'Test Key')

    result = await database.validate_api_key(raw_key)

    assert result is not None
    assert result['email'] == 'test@example.com'


@pytest.mark.asyncio
async def test_validate_invalid_api_key(db):
    """Test that invalid API key returns None."""
    result = await database.validate_api_key('invalid-key')
    assert result is None


@pytest.mark.asyncio
async def test_get_user_api_keys(db):
    """Test listing user's API keys."""
    user = await database.get_or_create_user(
        email='test@example.com',
        name='Test',
        picture=''
    )
    await database.create_api_key(user['id'], 'Key 1')
    await database.create_api_key(user['id'], 'Key 2')

    keys = await database.get_user_api_keys(user['id'])

    assert len(keys) == 2
    assert keys[0]['name'] in ['Key 1', 'Key 2']
    assert 'key_hash' not in keys[0]  # Should not expose hash


@pytest.mark.asyncio
async def test_delete_api_key(db):
    """Test deleting an API key."""
    user = await database.get_or_create_user(
        email='test@example.com',
        name='Test',
        picture=''
    )
    key_id, raw_key = await database.create_api_key(user['id'], 'Test Key')

    deleted = await database.delete_api_key(key_id, user['id'])
    assert deleted is True

    # Verify it's gone
    result = await database.validate_api_key(raw_key)
    assert result is None


@pytest.mark.asyncio
async def test_delete_api_key_wrong_user(db):
    """Test that user can't delete another user's key."""
    user1 = await database.get_or_create_user('user1@example.com', 'User1', '')
    user2 = await database.get_or_create_user('user2@example.com', 'User2', '')

    key_id, _ = await database.create_api_key(user1['id'], 'User1 Key')

    # User2 tries to delete User1's key
    deleted = await database.delete_api_key(key_id, user2['id'])
    assert deleted is False
