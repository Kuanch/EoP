# FastAPI Login Application

A simple web application with login authentication built with FastAPI.

## Features

- Login page with beautiful UI
- Session-based authentication
- Dashboard page after login
- Logout functionality
- Protected routes

## Current Credentials

- **Username**: admin
- **Password**: password

## Installation

1. Create a virtual environment:
```bash
python3 -m venv venv
```

2. Activate the virtual environment:
```bash
source venv/bin/activate  # On Linux/Mac
```

3. Install dependencies:
```bash
pip install fastapi uvicorn python-multipart jinja2
```

## Running the Application

```bash
python main.py
```

Or with uvicorn directly:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The application will be available at: http://localhost:8000

## Project Structure

```
fastapi-login-app/
├── main.py              # FastAPI application
├── templates/
│   ├── login.html      # Login page
│   └── index.html      # Dashboard page
├── static/             # Static files (CSS, JS, images)
├── venv/               # Virtual environment
└── README.md           # This file
```

## Security Notes

⚠️ **This is a basic implementation for development purposes.**

For production use, you should:
- Use proper password hashing (bcrypt)
- Implement CSRF protection
- Add rate limiting
- Use HTTPS
- Store sessions in a database or Redis
- Add security headers
- Implement proper logging
