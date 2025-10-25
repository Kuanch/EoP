#!/usr/bin/env python3
"""Test script to verify database authentication works."""

import sys
sys.path.insert(0, '/home/sixigma/fastapi-login-app')

from database import SessionLocal, authenticate_user

def test_authentication():
    """Test user authentication with database."""
    db = SessionLocal()
    try:
        # Test with correct credentials
        print("Testing authentication with admin/admin123...")
        user = authenticate_user(db, "admin", "admin123")
        if user:
            print(f"✅ Authentication successful!")
            print(f"   Username: {user.username}")
            print(f"   Email: {user.email}")
            print(f"   Active: {user.is_active}")
            print(f"   Last login: {user.last_login}")
        else:
            print("❌ Authentication failed!")
            return False

        # Test with wrong password
        print("\nTesting authentication with admin/wrongpassword...")
        user = authenticate_user(db, "admin", "wrongpassword")
        if user:
            print("❌ Error: Authentication should have failed!")
            return False
        else:
            print("✅ Correctly rejected wrong password")

        # Test with non-existent user
        print("\nTesting authentication with nonexistent/password...")
        user = authenticate_user(db, "nonexistent", "password")
        if user:
            print("❌ Error: Authentication should have failed!")
            return False
        else:
            print("✅ Correctly rejected non-existent user")

        print("\n✅ All authentication tests passed!")
        return True

    finally:
        db.close()

if __name__ == "__main__":
    success = test_authentication()
    sys.exit(0 if success else 1)
