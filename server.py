# server.py
import os
import mysql.connector
from fastmcp import FastMCP
from typing import List, Optional, Dict, Any
import re
from difflib import SequenceMatcher
import Levenshtein
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# -------------------------------
# MCP server
# -------------------------------
mcp = FastMCP("LeaveManager")

# -------------------------------
# MySQL connection for no password setup
# -------------------------------
def get_connection():
    try:
        # Try multiple connection methods
        connection_params = [
            # Method 1: No password parameter at all
            {
                "host": os.getenv("DB_HOST", "localhost"),
                "user": os.getenv("DB_USER", "root"), 
                "database": os.getenv("DB_NAME", "leave_db"),
                "connection_timeout": 10
            },
            # Method 2: Empty password
            {
                "host": os.getenv("DB_HOST", "localhost"),
                "user": os.getenv("DB_USER", "root"),
                "password": "",
                "database": os.getenv("DB_NAME", "leave_db"),
                "connection_timeout": 10
            }
        ]
        
        for params in connection_params:
            try:
                conn = mysql.connector.connect(**params)
                logger.info("✅ Database connection established successfully")
                return conn
            except mysql.connector.Error as e:
                logger.warning(f"Connection attempt failed: {e}")
                continue
        
        # If all methods fail
        logger.error("All database connection attempts failed")
        if os.getenv("ENVIRONMENT", "development") == "development":
            logger.warning("Using mock mode for development")
            return None
        raise mysql.connector.Error("Could not connect to database")
        
    except Exception as e:
        logger.error(f"Unexpected error during database connection: {e}")
        if os.getenv("ENVIRONMENT", "development") == "development":
            logger.warning("Using mock mode for development")
            return None
        raise

# -------------------------------
# AI-Powered Name Matching Utilities
# -------------------------------
class NameMatcher:
    @staticmethod
    def normalize_name(name: str) -> str:
        name = name.lower().strip()
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', ' ', name)
        return name
    
    @staticmethod
    def similarity_score(name1: str, name2: str) -> float:
        name1_norm = NameMatcher.normalize_name(name1)
        name2_norm = NameMatcher.normalize_name(name2)
        levenshtein_sim = 1 - (Levenshtein.distance(name1_norm, name2_norm) / max(len(name1_norm), len(name2_norm), 1))
        sequence_sim = SequenceMatcher(None, name1_norm, name2_norm).ratio()
        combined_score = (levenshtein_sim * 0.6) + (sequence_sim * 0.4)
        return combined_score
    
    @staticmethod
    def extract_name_parts(full_name: str) -> Dict[str, str]:
        parts = full_name.split()
        if len(parts) == 1:
            return {'first': parts[0], 'last': ''}
        elif len(parts) == 2:
            return {'first': parts[0], 'last': parts[1]}
        else:
            return {'first': parts[0], 'last': parts[-1]}
    
    @staticmethod
    def fuzzy_match_employee(search_name: str, employees: List[Dict[str, Any]], threshold: float = 0.6) -> List[Dict[str, Any]]:
        matches = []
        search_parts = NameMatcher.extract_name_parts(search_name)
        for emp in employees:
            emp_full = f"{emp['first_name']} {emp['last_name']}".strip()
            emp_first_last = f"{emp['first_name']} {emp['last_name']}"
            emp_last_first = f"{emp['last_name']} {emp['first_name']}"
            scores = [
                NameMatcher.similarity_score(search_name, emp_full),
                NameMatcher.similarity_score(search_name, emp_first_last),
                NameMatcher.similarity_score(search_name, emp_last_first),
            ]
            if search_parts['last']:
                first_score = NameMatcher.similarity_score(search_parts['first'], emp['first_name'])
                last_score = NameMatcher.similarity_score(search_parts['last'], emp['last_name'])
                scores.append((first_score + last_score) / 2)
            best = max(scores)
            if best >= threshold:
                matches.append({'employee': emp, 'score': best, 'match_type': 'fuzzy'})
        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches

# -------------------------------
# Enhanced Employee Search with AI
# -------------------------------
def fetch_employees_ai(search_term: str = None, emp_id: int = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if emp_id:
            cursor.execute("""
                SELECT employee_id, first_name, last_name, email, job_title, dept_id, 
                       hire_date, phone, address, status
                FROM employee 
                WHERE employee_id = %s
            """, (emp_id,))
        elif search_term:
            cursor.execute("""
                SELECT employee_id, first_name, last_name, email, job_title, dept_id, 
                       hire_date, phone, address, status
                FROM employee 
                WHERE first_name LIKE %s OR last_name LIKE %s 
                   OR CONCAT(first_name, ' ', last_name) LIKE %s
                ORDER BY first_name, last_name
            """, (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%"))
        else:
            return []

        rows = cursor.fetchall()
        if search_term and not rows:
            cursor.execute("""
                SELECT employee_id, first_name, last_name, email, job_title, dept_id, 
                       hire_date, phone, address, status
                FROM employee 
                WHERE status = 'Active'
            """)
            all_emp = cursor.fetchall()
            fuzzy = NameMatcher.fuzzy_match_employee(search_term, all_emp)
            rows = [m['employee'] for m in fuzzy[:5]]
        return rows
    except Exception as e:
        print(f"Database error: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

# -------------------------------
# Helper: Get department name
# -------------------------------
def get_department_name(dept_id: int) -> str:
    if not dept_id:
        return "Unknown"
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT dept_name FROM department WHERE dept_id = %s", (dept_id,))
        result = cursor.fetchone()
        return result[0] if result else "Unknown"
    except Exception:
        return "Unknown"
    finally:
        cursor.close()
        conn.close()

# -------------------------------
# Helper: Format employee options for display
# -------------------------------
def format_employee_options(employees: List[Dict[str, Any]]) -> str:
    options = []
    for i, emp in enumerate(employees, 1):
        dept_name = get_department_name(emp.get('dept_id'))
        option = f"{i}. 👤 {emp['first_name']} {emp['last_name']}"
        if emp.get('email'):
            option += f" | 📧 {emp['email']}"
        if emp.get('job_title'):
            option += f" | 💼 {emp['job_title']}"
        if dept_name != "Unknown":
            option += f" | 🏢 {dept_name}"
        if emp.get('employee_id'):
            option += f" | 🆔 {emp['employee_id']}"
        options.append(option)
    return "\n".join(options)

# -------------------------------
# AI-Powered Employee Resolution
# -------------------------------
def resolve_employee_ai(search_name: str, additional_context: str = None) -> Dict[str, Any]:
    employees = fetch_employees_ai(search_term=search_name)
    if not employees:
        return {'status': 'not_found', 'message': f"No employees found matching '{search_name}'"}
    if len(employees) == 1:
        return {'status': 'resolved', 'employee': employees[0]}
    if additional_context:
        ctx = additional_context.lower()
        filtered = []
        for emp in employees:
            dept_name = get_department_name(emp.get('dept_id')).lower()
            job = (emp.get('job_title') or '').lower()
            email = (emp.get('email') or '').lower()
            lastn = emp['last_name'].lower()
            if (ctx in dept_name or ctx in job or ctx in email or ctx == lastn):
                filtered.append(emp)
        if len(filtered) == 1:
            return {'status': 'resolved', 'employee': filtered[0]}
    return {
        'status': 'ambiguous',
        'employees': employees,
        'message': f"Found {len(employees)} employees. Please specify:"
    }

# -------------------------------
# Tool: Get Leave Balance
# -------------------------------
@mcp.tool()
def get_leave_balance(name: str, additional_context: Optional[str] = None) -> str:
    resolution = resolve_employee_ai(name, additional_context)
    if resolution['status'] == 'not_found':
        return f"❌ No employee found matching '{name}'."
    if resolution['status'] == 'ambiguous':
        options_text = format_employee_options(resolution['employees'])
        return f"🔍 {resolution['message']}\n\n{options_text}\n\n💡 Tip: You can specify by:\n- Last name (e.g., 'Smith')\n- Department (e.g., 'Engineering')\n- Email domain\n- Or say the number (e.g., '1')"
    emp = resolution['employee']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT balance FROM employees WHERE name = %s OR email = %s",
                       (emp['first_name'], emp['email']))
        balance_result = cursor.fetchone()
        if balance_result:
            balance = balance_result['balance']
            dept_name = get_department_name(emp.get('dept_id'))
            return f"✅ **{emp['first_name']} {emp['last_name']}**\n" \
                   f"🆔 ID: {emp['employee_id']} | 🏢 {dept_name}\n" \
                   f"💼 {emp.get('job_title', 'N/A')}\n" \
                   f"📧 {emp.get('email', 'N/A')}\n" \
                   f"📊 **Leave Balance: {balance} days**"
        else:
            return f"ℹ️  Found employee but no leave balance data available for {emp['first_name']} {emp['last_name']}"
    except Exception as e:
        return f"❌ Error retrieving leave balance: {str(e)}"
    finally:
        cursor.close()
        conn.close()

# -------------------------------
# Tool: Smart Employee Search
# -------------------------------
@mcp.tool()
def smart_employee_search(search_query: str, search_type: str = "auto") -> str:
    query_lower = search_query.lower().strip()
    if "from" in query_lower:
        parts = query_lower.split(" from ")
        name_part = parts[0].strip()
        dept_part = parts[1].strip() if len(parts) > 1 else None
    elif "in" in query_lower:
        parts = query_lower.split(" in ")
        name_part = parts[0].strip()
        dept_part = parts[1].strip() if len(parts) > 1 else None
    else:
        name_part = query_lower
        dept_part = None

    resolution = resolve_employee_ai(name_part, dept_part)
    if resolution['status'] == 'not_found':
        employees = fetch_employees_ai(search_term=search_query)
        if employees:
            options_text = format_employee_options(employees[:5])
            return f"🔍 Found potential matches for '{search_query}':\n\n{options_text}"
        return f"❌ No employees found matching '{search_query}'"
    if resolution['status'] == 'ambiguous':
        options_text = format_employee_options(resolution['employees'])
        return f"🔍 Multiple matches found for '{search_query}':\n\n{options_text}"
    emp = resolution['employee']
    dept_name = get_department_name(emp.get('dept_id'))
    return f"✅ **Match Found!**\n\n" \
           f"👤 **{emp['first_name']} {emp['last_name']}**\n" \
           f"🆔 Employee ID: {emp['employee_id']}\n" \
           f"🏢 Department: {dept_name}\n" \
           f"💼 Position: {emp.get('job_title', 'N/A')}\n" \
           f"📧 Email: {emp.get('email', 'N/A')}\n" \
           f"📅 Hire Date: {emp.get('hire_date', 'N/A')}\n" \
           f"📞 Phone: {emp.get('phone', 'N/A')}\n" \
           f"🔰 Status: {emp.get('status', 'N/A')}"

# -------------------------------
# Tool: Apply Leave
# -------------------------------
@mcp.tool()
def apply_leave_ai(employee_query: str, leave_dates: List[str], additional_context: Optional[str] = None) -> str:
    resolution = resolve_employee_ai(employee_query, additional_context)
    if resolution['status'] == 'not_found':
        return f"❌ No employee found matching '{employee_query}'."
    if resolution['status'] == 'ambiguous':
        options_text = format_employee_options(resolution['employees'])
        return f"🔍 Multiple employees found. Please specify:\n\n{options_text}"
    emp = resolution['employee']
    return f"✅ Leave application prepared for {emp['first_name']} {emp['last_name']}\n" \
           f"📅 Dates: {', '.join(leave_dates)}\n" \
           f"🆔 Employee ID: {emp['employee_id']}\n" \
           f"💼 Department: {get_department_name(emp.get('dept_id'))}"

# -------------------------------
# Resource: AI Assistant
# -------------------------------
@mcp.resource("ai_assistant://{query}")
def ai_assistant_help(query: str) -> str:
    help_text = """
🤖 **AI-Powered Leave Management Assistant**

I can help you with:

🔍 **Smart Employee Search**
- "Find John Smith"
- "Search for Priya in Engineering" 
- "Who is Kumar from IT?"
- "Find employees in Sales"

📊 **Leave Management**
- "Get leave balance for John"
- "Check Priya's leave balance"
- "Apply leave for Smith"

💡 **Tips for Better Results:**
- Use full names when possible: "John Smith"
- Specify department: "Priya from HR"
- Use email domains: "john@company.com"
- Mention job roles: "Manager Smith"
    """
    return help_text

# -------------------------------
# Run MCP server
# -------------------------------
if __name__ == "__main__":
    mcp.run(transport='stdio') 

