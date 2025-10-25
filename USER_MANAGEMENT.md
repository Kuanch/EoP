# User Management Guide

This document explains the SQLite-based user management system implemented for the FastAPI login application.

## Overview

The application now uses SQLite database for user authentication instead of hardcoded credentials. This provides:

- Scalable user management (suitable for <10 users)
- Persistent user data across server restarts
- User activity tracking (creation date, last login)
- Account activation/deactivation
- Password changes
- Email storage (optional)

## Database Schema

### User Table

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key (auto-increment) |
| username | String(50) | Unique username (indexed) |
| password_hash | String(128) | Bcrypt hashed password |
| email | String(100) | Email address (optional, unique, indexed) |
| is_active | Boolean | Account active status (default: True) |
| created_at | DateTime | Account creation timestamp |
| last_login | DateTime | Last successful login timestamp |

## User Management CLI

The `manage_users.py` script provides a command-line interface for managing users.

### Commands

#### Initialize Database

```bash
venv/bin/python manage_users.py init
```

Creates the database and tables. Run this once before using the application.

#### Create User

```bash
venv/bin/python manage_users.py create <username>
```

Creates a new user with interactive password prompt. Example:

```bash
venv/bin/python manage_users.py create admin
# Enter password for 'admin': ********
# Confirm password: ********
# Enter email (optional, press Enter to skip): admin@example.com
# ✅ User 'admin' created successfully!
```

**Password Requirements:**
- Minimum 8 characters
- Passwords are hashed with bcrypt (unique salt per password)

#### List Users

```bash
venv/bin/python manage_users.py list
```

Displays all users with details:

```
ID    Username             Email                          Active   Created              Last Login
--------------------------------------------------------------------------------------------------------------
1     admin                admin@example.com              ✅        2025-10-25 05:48     2025-10-25 05:51
2     testuser             test@example.com               ❌        2025-10-25 06:00     Never

Total users: 2
```

#### Show User Info

```bash
venv/bin/python manage_users.py info <username>
```

Shows detailed information for a specific user.

#### Change Password

```bash
venv/bin/python manage_users.py password <username>
```

Changes a user's password with interactive prompt:

```bash
venv/bin/python manage_users.py password admin
# Enter new password for 'admin': ********
# Confirm new password: ********
# ✅ Password for 'admin' changed successfully!
```

#### Deactivate User

```bash
venv/bin/python manage_users.py deactivate <username>
```

Disables a user account (prevents login without deleting data).

#### Activate User

```bash
venv/bin/python manage_users.py activate <username>
```

Re-enables a deactivated user account.

#### Delete User

```bash
venv/bin/python manage_users.py delete <username>
```

Permanently deletes a user account (requires confirmation):

```bash
venv/bin/python manage_users.py delete testuser
# ⚠️  Are you sure you want to delete user 'testuser'? (yes/no): yes
# ✅ User 'testuser' deleted successfully!
```

## Authentication Flow

### How It Works

1. **User Login Request**: User submits username and password via login form
2. **Database Lookup**: Application queries database for user by username
3. **Validation Checks**:
   - User exists in database
   - User account is active (`is_active = True`)
   - Password matches bcrypt hash in database
4. **Success**: Creates session, updates `last_login` timestamp, redirects to dashboard
5. **Failure**: Records failed attempt for rate limiting, shows error message

### Code Integration

#### main.py Changes

**Before (hardcoded credentials):**
```python
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = bcrypt.hashpw("password".encode('utf-8'), bcrypt.gensalt())

if username == ADMIN_USERNAME and verify_password(password, ADMIN_PASSWORD_HASH):
    # Success
```

**After (database authentication):**
```python
from database import get_db, authenticate_user

async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, username, password)
    if user:
        # Success - user object contains username, email, etc.
```

### Security Features

All existing security features remain intact:

- **Password Hashing**: Bcrypt with unique salt per password (from security1 branch)
- **CSRF Protection**: Token validation on login (from security1 branch)
- **Rate Limiting**:
  - 10 requests/minute per IP (endpoint-level)
  - 5 failed login attempts per 15 minutes (application-level)
- **Secure Cookies**: httponly, secure, samesite=strict (from tls-https branch)
- **Security Headers**: HSTS, X-Frame-Options, etc. (from tls-https branch)

## Database File

- **Location**: `/home/sixigma/fastapi-login-app/users.db`
- **Format**: SQLite3
- **Excluded from Git**: Already in `.gitignore` (*.db pattern)

### Backup and Recovery

To backup user database:

```bash
cp users.db users.db.backup
```

To restore from backup:

```bash
cp users.db.backup users.db
```

To reset database (deletes all users):

```bash
rm users.db
venv/bin/python manage_users.py init
```

## Migration from Hardcoded Credentials

The migration removed:
- `ADMIN_USERNAME` constant
- `ADMIN_PASSWORD_HASH` constant
- `verify_password()` function (moved to User model)

Password verification is now handled by the `User.check_password()` method in `database.py`.

## Limitations

This SQLite-based system is suitable for:
- Small deployments (<10 users)
- Single-server applications
- Low to moderate traffic

**Not suitable for:**
- High-traffic applications (use PostgreSQL/MySQL)
- Multi-server deployments (SQLite doesn't support concurrent writes well)
- Applications requiring advanced user features (roles, permissions, etc.)

## Troubleshooting

### "No such table: users"

**Cause**: Database not initialized
**Solution**: Run `venv/bin/python manage_users.py init`

### "User already exists"

**Cause**: Trying to create user with duplicate username or email
**Solution**: Use different username/email or delete existing user

### "Authentication failed" but password is correct

**Possible causes:**
1. User account is deactivated
   - **Solution**: `venv/bin/python manage_users.py activate <username>`
2. Wrong username (usernames are case-sensitive)
   - **Solution**: Check exact username with `list` command
3. Database file corrupted
   - **Solution**: Restore from backup or recreate database

### Login works in test but not in browser

**Cause**: Database session handling or CSRF token issue
**Check:**
1. Verify FastAPI app is running: `curl http://localhost:8000/login`
2. Check logs for errors: Look at console where `python main.py` is running
3. Verify database has users: `venv/bin/python manage_users.py list`

## Testing

### Test Script

A test script is included to verify authentication:

```bash
venv/bin/python test_login.py
```

This tests:
- Successful authentication with correct credentials
- Failed authentication with wrong password
- Failed authentication with non-existent user
- Last login timestamp update

### Manual Testing

1. Create a test user:
   ```bash
   venv/bin/python manage_users.py create testuser
   ```

2. Start the application:
   ```bash
   venv/bin/python main.py
   ```

3. Visit http://localhost:8000/login in browser

4. Login with test credentials

5. Verify login timestamp updated:
   ```bash
   venv/bin/python manage_users.py info testuser
   ```

## Next Steps

Future enhancements could include:

1. **User Roles**: Add admin/user role system
2. **Password Reset**: Email-based password reset flow
3. **Two-Factor Authentication**: TOTP or SMS verification
4. **Login History**: Track all login attempts (not just last login)
5. **Session Management**: View and revoke active sessions
6. **PostgreSQL Migration**: For larger deployments

## Files

- `database.py` - Database models and helper functions
- `manage_users.py` - CLI tool for user management
- `main.py` - FastAPI application with database authentication
- `users.db` - SQLite database file (excluded from git)
- `test_login.py` - Automated authentication tests
- `USER_MANAGEMENT.md` - This documentation
