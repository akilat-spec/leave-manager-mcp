# main.py (updated for production)
import mysql.connector
from fastmcp import FastMCP
from typing import List, Optional, Dict, Any
import re
from difflib import SequenceMatcher
import Levenshtein
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------
# MCP server
# -------------------------------
mcp = FastMCP("LeaveManager")

# -------------------------------
# MySQL connection (Production-ready)
# -------------------------------
def get_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'leave_db'),
        port=os.getenv('DB_PORT', '3306')
    )

# -------------------------------
# Database Initialization
# -------------------------------
def init_database():
    """Initialize database tables if they don't exist"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Create employee table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS employee (
                employee_id INT AUTO_INCREMENT PRIMARY KEY,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                email VARCHAR(255) UNIQUE,
                job_title VARCHAR(200),
                dept_id INT,
                hire_date DATE,
                phone VARCHAR(20),
                address TEXT,
                status ENUM('Active', 'Inactive') DEFAULT 'Active',
                balance INT DEFAULT 20,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create department table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS department (
                dept_id INT AUTO_INCREMENT PRIMARY KEY,
                dept_name VARCHAR(100) NOT NULL,
                manager_id INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create leave_records table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leave_records (
                leave_id INT AUTO_INCREMENT PRIMARY KEY,
                employee_id INT,
                leave_type ENUM('Sick', 'Vacation', 'Personal', 'Other'),
                start_date DATE,
                end_date DATE,
                status ENUM('Pending', 'Approved', 'Rejected') DEFAULT 'Pending',
                reason TEXT,
                applied_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (employee_id) REFERENCES employee(employee_id)
            )
        """)
        
        conn.commit()
        logger.info("Database tables initialized successfully")
        
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
    finally:
        cursor.close()
        conn.close()

# ... [rest of your existing code remains the same]

# -------------------------------
# Run MCP server
# -------------------------------
if __name__ == "__main__":
    # Initialize database
    init_database()
    
    # Install required package if not available
    try:
        import Levenshtein
    except ImportError:
        print("Please install python-levenshtein: pip install python-levenshtein")
    
    mcp.run(transport='stdio')