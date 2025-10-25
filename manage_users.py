#!/usr/bin/env python3
"""User management CLI tool."""

import sys
import getpass
from database import (
    init_db, SessionLocal, create_user, list_users,
    delete_user, change_password, activate_user,
    deactivate_user, get_user_by_username
)


def print_help():
    """Print help message."""
    print("""
User Management CLI

Usage:
    python manage_users.py <command> [arguments]

Commands:
    init                    Initialize the database
    create <username>       Create a new user (will prompt for password)
    list                    List all users
    delete <username>       Delete a user
    password <username>     Change user password
    activate <username>     Activate a user account
    deactivate <username>   Deactivate a user account
    info <username>         Show user information

Examples:
    python manage_users.py init
    python manage_users.py create admin
    python manage_users.py list
    python manage_users.py password admin
    python manage_users.py delete testuser
    """)


def cmd_init():
    """Initialize database."""
    init_db()
    print("✅ Database initialized successfully!")
    print("📁 Database file: users.db")


def cmd_create(username):
    """Create a new user."""
    db = SessionLocal()
    try:
        # Check if user exists
        existing = get_user_by_username(db, username)
        if existing:
            print(f"❌ Error: User '{username}' already exists!")
            return

        # Get password
        password = getpass.getpass(f"Enter password for '{username}': ")
        password_confirm = getpass.getpass("Confirm password: ")

        if password != password_confirm:
            print("❌ Error: Passwords don't match!")
            return

        if len(password) < 8:
            print("❌ Error: Password must be at least 8 characters!")
            return

        # Get email (optional)
        email = input("Enter email (optional, press Enter to skip): ").strip()
        email = email if email else None

        # Create user
        user = create_user(db, username, password, email)
        print(f"✅ User '{user.username}' created successfully!")
        if email:
            print(f"📧 Email: {email}")

    finally:
        db.close()


def cmd_list():
    """List all users."""
    db = SessionLocal()
    try:
        users = list_users(db)
        if not users:
            print("No users found.")
            return

        print(f"\n{'ID':<5} {'Username':<20} {'Email':<30} {'Active':<8} {'Created':<20} {'Last Login':<20}")
        print("-" * 110)

        for user in users:
            status = "✅" if user.is_active else "❌"
            email = user.email or "-"
            created = user.created_at.strftime("%Y-%m-%d %H:%M")
            last_login = user.last_login.strftime("%Y-%m-%d %H:%M") if user.last_login else "Never"

            print(f"{user.id:<5} {user.username:<20} {email:<30} {status:<8} {created:<20} {last_login:<20}")

        print(f"\nTotal users: {len(users)}")

    finally:
        db.close()


def cmd_delete(username):
    """Delete a user."""
    confirm = input(f"⚠️  Are you sure you want to delete user '{username}'? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Cancelled.")
        return

    db = SessionLocal()
    try:
        if delete_user(db, username):
            print(f"✅ User '{username}' deleted successfully!")
        else:
            print(f"❌ Error: User '{username}' not found!")
    finally:
        db.close()


def cmd_password(username):
    """Change user password."""
    db = SessionLocal()
    try:
        user = get_user_by_username(db, username)
        if not user:
            print(f"❌ Error: User '{username}' not found!")
            return

        new_password = getpass.getpass(f"Enter new password for '{username}': ")
        password_confirm = getpass.getpass("Confirm new password: ")

        if new_password != password_confirm:
            print("❌ Error: Passwords don't match!")
            return

        if len(new_password) < 8:
            print("❌ Error: Password must be at least 8 characters!")
            return

        if change_password(db, username, new_password):
            print(f"✅ Password for '{username}' changed successfully!")
        else:
            print(f"❌ Error: Could not change password!")

    finally:
        db.close()


def cmd_activate(username):
    """Activate a user account."""
    db = SessionLocal()
    try:
        if activate_user(db, username):
            print(f"✅ User '{username}' activated successfully!")
        else:
            print(f"❌ Error: User '{username}' not found!")
    finally:
        db.close()


def cmd_deactivate(username):
    """Deactivate a user account."""
    db = SessionLocal()
    try:
        if deactivate_user(db, username):
            print(f"✅ User '{username}' deactivated successfully!")
        else:
            print(f"❌ Error: User '{username}' not found!")
    finally:
        db.close()


def cmd_info(username):
    """Show user information."""
    db = SessionLocal()
    try:
        user = get_user_by_username(db, username)
        if not user:
            print(f"❌ Error: User '{username}' not found!")
            return

        print(f"\n📋 User Information")
        print("-" * 40)
        print(f"ID:          {user.id}")
        print(f"Username:    {user.username}")
        print(f"Email:       {user.email or 'Not set'}")
        print(f"Active:      {'Yes ✅' if user.is_active else 'No ❌'}")
        print(f"Created:     {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Last Login:  {user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else 'Never'}")
        print()

    finally:
        db.close()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == 'help' or command == '--help' or command == '-h':
        print_help()

    elif command == 'init':
        cmd_init()

    elif command == 'create':
        if len(sys.argv) < 3:
            print("❌ Error: Username required!")
            print("Usage: python manage_users.py create <username>")
            sys.exit(1)
        cmd_create(sys.argv[2])

    elif command == 'list':
        cmd_list()

    elif command == 'delete':
        if len(sys.argv) < 3:
            print("❌ Error: Username required!")
            print("Usage: python manage_users.py delete <username>")
            sys.exit(1)
        cmd_delete(sys.argv[2])

    elif command == 'password':
        if len(sys.argv) < 3:
            print("❌ Error: Username required!")
            print("Usage: python manage_users.py password <username>")
            sys.exit(1)
        cmd_password(sys.argv[2])

    elif command == 'activate':
        if len(sys.argv) < 3:
            print("❌ Error: Username required!")
            print("Usage: python manage_users.py activate <username>")
            sys.exit(1)
        cmd_activate(sys.argv[2])

    elif command == 'deactivate':
        if len(sys.argv) < 3:
            print("❌ Error: Username required!")
            print("Usage: python manage_users.py deactivate <username>")
            sys.exit(1)
        cmd_deactivate(sys.argv[2])

    elif command == 'info':
        if len(sys.argv) < 3:
            print("❌ Error: Username required!")
            print("Usage: python manage_users.py info <username>")
            sys.exit(1)
        cmd_info(sys.argv[2])

    else:
        print(f"❌ Error: Unknown command '{command}'")
        print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
