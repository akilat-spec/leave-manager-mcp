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
    Levenshtein = None  # fallback if not installed

# For health route responses
from starlette.requests import Request
from starlette.responses import PlainTextResponse

# -------------------------------
# MCP server
# -------------------------------
mcp = FastMCP("LeaveManager")

# -------------------------------
# MySQL connection
# -------------------------------
def get_connection():
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        parsed = urllib.parse.urlparse(db_url)
        return mysql.connector.connect(
            host=parsed.hostname or "103.174.10.72",
            user=parsed.username or "leave_mcp",
            password=parsed.password or "PY@4rjQu%ha0byc7",
            database=(parsed.path.lstrip("/") if parsed.path else "leave_mcp"),
            port=parsed.port or 3306
        )
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "103.174.10.72"),
        user=os.environ.get("DB_USER", "leave_mcp"),
        password=os.environ.get("DB_PASSWORD", "PY@4rjQu%ha0byc7"),
        database=os.environ.get("DB_NAME", "leave_mcp"),
        port=int(os.environ.get("DB_PORT", 3306))
    )

# -------------------------------
# Name Matching Utilities
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
        n1 = NameMatcher.normalize_name(name1)
        n2 = NameMatcher.normalize_name(name2)
        if Levenshtein:
            lev_sim = 1 - Levenshtein.distance(n1, n2) / max(len(n1), len(n2), 1)
        else:
            lev_sim = SequenceMatcher(None, n1, n2).ratio()
        seq_sim = SequenceMatcher(None, n1, n2).ratio()
        return 0.6 * lev_sim + 0.4 * seq_sim

    @staticmethod
    def extract_name_parts(full_name: str) -> Dict[str,str]:
        parts = full_name.split()
        return {'first': parts[0], 'last': parts[-1] if len(parts)>1 else ''}

    @staticmethod
    def fuzzy_match_employee(search_name: str, employees: List[Dict[str,Any]], threshold: float=0.6) -> List[Dict[str,Any]]:
        matches = []
        parts = NameMatcher.extract_name_parts(search_name)
        for emp in employees:
            scores = []
            full_emp_name = f"{emp.get('first_name','')} {emp.get('last_name','')}"
            scores.append(NameMatcher.similarity_score(search_name, full_emp_name))
            if parts['last']:
                scores.append((NameMatcher.similarity_score(parts['first'], emp.get('first_name','')) +
                               NameMatcher.similarity_score(parts['last'], emp.get('last_name',''))) / 2)
            best_score = max(scores)
            if best_score >= threshold:
                matches.append({'employee': emp, 'score': best_score})
        matches.sort(key=lambda x: x['score'], reverse=True)
        return [m['employee'] for m in matches]

# -------------------------------
# Fetch Employees
# -------------------------------
def fetch_employees_ai(search_term: str = None, emp_id: int = None) -> List[Dict[str,Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if emp_id:
            cursor.execute("SELECT * FROM employee WHERE employee_id=%s", (emp_id,))
            return cursor.fetchall()
        elif search_term:
            cursor.execute("""
                SELECT * FROM employee 
                WHERE first_name LIKE %s OR last_name LIKE %s OR CONCAT(first_name,' ',last_name) LIKE %s
            """, (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%"))
            rows = cursor.fetchall()
            if not rows:
                cursor.execute("SELECT * FROM employee WHERE status='Active'")
                all_emps = cursor.fetchall()
                rows = NameMatcher.fuzzy_match_employee(search_term, all_emps)[:5]
            return rows
        else:
            return []
    finally:
        cursor.close()
        conn.close()

# -------------------------------
# Helper Functions
# -------------------------------
def get_department_name(dept_id: int) -> str:
    if not dept_id: return "Unknown"
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT dept_name FROM department WHERE dept_id=%s", (dept_id,))
        result = cursor.fetchone()
        return result[0] if result else "Unknown"
    finally:
        cursor.close()
        conn.close()

def format_employee_options(employees: List[Dict[str,Any]]) -> str:
    options = []
    for i, emp in enumerate(employees,1):
        dept = get_department_name(emp.get('dept_id'))
        opt = f"{i}. {emp.get('first_name')} {emp.get('last_name')} | {emp.get('email')} | {emp.get('job_title')} | {dept} | ID: {emp.get('employee_id')}"
        options.append(opt)
    return "\n".join(options)

# -------------------------------
# Resolve Employee AI
# -------------------------------
def resolve_employee_ai(search_name: str, additional_context: str = None) -> Dict[str,Any]:
    employees = fetch_employees_ai(search_name)
    if not employees:
        return {'status':'not_found', 'message':f"No employees found matching '{search_name}'"}
    if len(employees) == 1:
        return {'status':'resolved','employee':employees[0]}

    if additional_context:
        context = additional_context.lower()
        filtered = []
        for emp in employees:
            dept = get_department_name(emp.get('dept_id')).lower()
            job = (emp.get('job_title') or '').lower()
            email = (emp.get('email') or '').lower()
            lname = emp.get('last_name','').lower()
            if context in dept or context in job or context in email or context == lname:
                filtered.append(emp)
        if len(filtered) == 1:
            return {'status':'resolved','employee':filtered[0]}
        elif filtered:
            return {'status':'ambiguous','employees':filtered,'message':f"Found {len(filtered)} matching '{search_name}'"}

    return {'status':'ambiguous','employees':employees,'message':f"Found {len(employees)} employees with name containing '{search_name}'"}

# -------------------------------
# MCP Tools
# -------------------------------
@mcp.tool()
def get_leave_balance(name: str, additional_context: Optional[str]=None) -> str:
    resolution = resolve_employee_ai(name, additional_context)
    if resolution['status']=='not_found':
        return f"❌ No employee found matching '{name}'"
    if resolution['status']=='ambiguous':
        return f"⚠ {resolution['message']}\n\n{format_employee_options(resolution['employees'])}"

    emp = resolution['employee']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT balance FROM leave_balance WHERE employee_id=%s", (emp['employee_id'],))
        result = cursor.fetchone()
        if result:
            balance = result['balance']
            dept = get_department_name(emp.get('dept_id'))
            return f"✅ {emp['first_name']} {emp['last_name']} | Dept: {dept} | Role: {emp.get('job_title')} | Leave Balance: {balance} days"
        return f"ℹ️ Found employee but no leave balance record."
    finally:
        cursor.close()
        conn.close()

@mcp.tool()
def smart_employee_search(search_query: str) -> str:
    resolution = resolve_employee_ai(search_query)
    if resolution['status']=='not_found':
        emps = fetch_employees_ai(search_query)
        if emps:
            return f"🔍 Potential matches:\n{format_employee_options(emps[:5])}"
        return f"❌ No employees found matching '{search_query}'"
    if resolution['status']=='ambiguous':
        return f"🔍 Multiple matches found:\n{format_employee_options(resolution['employees'])}"
    emp = resolution['employee']
    dept = get_department_name(emp.get('dept_id'))
    return f"✅ Match Found: {emp['first_name']} {emp['last_name']} | Dept: {dept} | Role: {emp.get('job_title')} | Email: {emp.get('email')}"

@mcp.tool()
def apply_leave_ai(employee_query: str, leave_dates: List[str], leave_type: str = "Annual", reason: str = "", additional_context: Optional[str]=None) -> str:
    resolution = resolve_employee_ai(employee_query, additional_context)
    if resolution['status']=='not_found':
        return f"❌ No employee found matching '{employee_query}'"
    if resolution['status']=='ambiguous':
        return f"🔍 Multiple employees found. Please specify:\n{format_employee_options(resolution['employees'])}"
    
    emp = resolution['employee']
    conn = get_connection()
    cursor = conn.cursor()
    try:
        leave_dates_str = ",".join(leave_dates)
        cursor.execute("""
            INSERT INTO leave_applications (employee_id, employee_name, leave_dates, leave_type, reason, status)
            VALUES (%s, %s, %s, %s, %s, 'Pending')
        """, (emp['employee_id'], f"{emp['first_name']} {emp['last_name']}", leave_dates_str, leave_type, reason))
        conn.commit()
        return f"✅ Leave application submitted for {emp['first_name']} {emp['last_name']} | Dates: {leave_dates_str} | Type: {leave_type}"
    finally:
        cursor.close()
        conn.close()

# -------------------------------
# AI Assistant Resource
# -------------------------------
@mcp.resource("ai_assistant://{query}")
def ai_assistant_help(query:str) -> str:
    return """
🤖 AI-Powered Leave Assistant
Commands you can try:

🔍 Smart Employee Search:
- "Find John Smith"
- "Search for Priya in Engineering" 

📊 Leave Management:
- "Get leave balance for John"
- "Apply leave for Smith"
"""

# -------------------------------
# Health Route
# -------------------------------
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

# -------------------------------
# Run MCP Server
# -------------------------------
if __name__=="__main__":
    if Levenshtein is None:
        print("⚠ Warning: python-levenshtein not installed. Fuzzy matching may be lower.")
    transport = os.environ.get("MCP_TRANSPORT","streamable-http")
    host = os.environ.get("MCP_HOST","0.0.0.0")
    port = int(os.environ.get("PORT",8080))
    mcp.run(transport=transport, host=host, port=port)
