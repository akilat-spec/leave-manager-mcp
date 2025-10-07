# main.py
import os
import re
import urllib.parse
from typing import List, Optional, Dict, Any
from difflib import SequenceMatcher

# third-party
import mysql.connector
from fastmcp import FastMCP

# optional Levenshtein import
try:
    import Levenshtein
except ImportError:
    Levenshtein = None  # we'll check later

# For health route responses (used by FastMCP custom_route)
from starlette.requests import Request
from starlette.responses import PlainTextResponse

# -------------------------------
# MCP server
# -------------------------------
mcp = FastMCP("LeaveManager")

# -------------------------------
# MySQL connection (reads from env)
# -------------------------------
def get_connection():
    """
    Read DB credentials from DATABASE_URL (mysql://user:pass@host:port/dbname)
    or from DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT.
    """
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        parsed = urllib.parse.urlparse(db_url)
        return mysql.connector.connect(
            host=parsed.hostname or "103.174.10.72",
            user=parsed.username or "leave_mcp",
            password=parsed.password or "PY@4rjQu%ha0byc7",
            database=(parsed.path.lstrip("/") if parsed.path else ""),
            port=parsed.port or 3306,
        )

    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "103.174.10.72"),
        user=os.environ.get("DB_USER", "leave_mcp"),
        password=os.environ.get("DB_PASSWORD", "PY@4rjQu%ha0byc7"),
        database=os.environ.get("DB_NAME", "leave_mcp"),
        port=int(os.environ.get("DB_PORT", "3306")),
    )

# -------------------------------
# AI-Powered Name Matching Utilities
# (your original code preserved, unchanged logic)
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

        # If Levenshtein is available, use it; otherwise fall back to simple ratio
        if Levenshtein:
            levenshtein_sim = 1 - (Levenshtein.distance(name1_norm, name2_norm) / max(len(name1_norm), len(name2_norm), 1))
        else:
            # naive fallback: approximate by SequenceMatcher
            levenshtein_sim = SequenceMatcher(None, name1_norm, name2_norm).ratio()

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
            scores = []
            emp_full_name = f"{emp.get('first_name','')} {emp.get('last_name','')}".strip()
            scores.append(NameMatcher.similarity_score(search_name, emp_full_name))
            scores.append(NameMatcher.similarity_score(search_name, f"{emp.get('first_name','')} {emp.get('last_name','')}"))
            scores.append(NameMatcher.similarity_score(search_name, f"{emp.get('last_name','')} {emp.get('first_name','')}"))

            if search_parts['last']:
                first_score = NameMatcher.similarity_score(search_parts['first'], emp.get('first_name',''))
                last_score = NameMatcher.similarity_score(search_parts['last'], emp.get('last_name',''))
                scores.append((first_score + last_score) / 2)

            best_score = max(scores)
            if best_score >= threshold:
                matches.append({'employee': emp, 'score': best_score, 'match_type': 'fuzzy'})

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
            all_employees = cursor.fetchall()
            fuzzy_matches = NameMatcher.fuzzy_match_employee(search_term, all_employees)
            rows = [match['employee'] for match in fuzzy_matches[:5]]

        return rows

    except Exception as e:
        print(f"Database error: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

# -------------------------------
# Helpers: dept name & formatting
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
    except:
        return "Unknown"
    finally:
        cursor.close()
        conn.close()

def format_employee_options(employees: List[Dict[str, Any]]) -> str:
    options = []
    for i, emp in enumerate(employees, 1):
        dept_name = get_department_name(emp.get('dept_id'))
        option = f"{i}. 👤 {emp.get('first_name','')} {emp.get('last_name','')}"
        if emp.get('email'):
            option += f" | 📧 {emp.get('email')}"
        if emp.get('job_title'):
            option += f" | 💼 {emp.get('job_title')}"
        if dept_name != "Unknown":
            option += f" | 🏢 {dept_name}"
        if emp.get('employee_id'):
            option += f" | 🆔 {emp.get('employee_id')}"
        options.append(option)
    return "\n".join(options)

# -------------------------------
# Resolve & tools (unchanged logic)
# -------------------------------
def resolve_employee_ai(search_name: str, additional_context: str = None) -> Dict[str, Any]:
    employees = fetch_employees_ai(search_term=search_name)

    if not employees:
        return {'status': 'not_found', 'message': f"No employees found matching '{search_name}'"}

    if len(employees) == 1:
        return {'status': 'resolved', 'employee': employees[0]}

    if additional_context:
        context_lower = additional_context.lower()
        filtered_employees = []
        for emp in employees:
            dept_name = get_department_name(emp.get('dept_id')).lower()
            job_title = (emp.get('job_title') or '').lower()
            email = (emp.get('email') or '').lower()
            last_name = emp.get('last_name', '').lower()
            if (context_lower in dept_name or context_lower in job_title or context_lower in email or context_lower == last_name):
                filtered_employees.append(emp)
        if len(filtered_employees) == 1:
            return {'status': 'resolved', 'employee': filtered_employees[0]}

    return {
        'status': 'ambiguous',
        'employees': employees,
        'message': f"Found {len(employees)} employees. Please specify:"
    }

# -------------------------------
# MCP tools
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
        cursor.execute("SELECT balance FROM leave_balance WHERE name = %s OR email = %s",
                       (emp.get('first_name'), emp.get('email')))
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
# AI Assistant Resource
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

📊 **Leave Management**
- "Get leave balance for John"
- "Apply leave for Smith"
    """
    return help_text

# -------------------------------
# Health check route (HTTP only)
# -------------------------------
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

# -------------------------------
# Run MCP server (transport chosen via env)
# -------------------------------
if __name__ == "__main__":
    # Optional: warn if Levenshtein missing
    if Levenshtein is None:
        print("Warning: python-levenshtein not installed. Fuzzy quality will be slightly lower. Install with: pip install python-levenshtein")

    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")  # "stdio" for desktop, "streamable-http" for cloud
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))

    # Run: streamable-http (http) for cloud; stdio for local/desktop
    mcp.run(transport=transport, host=host, port=port)
