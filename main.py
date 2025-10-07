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

# For HTTP health check route
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
            host=parsed.hostname or "leave-manager-mcp/smithery.yaml",
            user=parsed.username or "leave_mcp",
            password=parsed.password or "",
            database=(parsed.path.lstrip("/") if parsed.path else ""),
            port=parsed.port or 3306,
        )
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "103.174.10.72"),
        user=os.environ.get("DB_USER", "leave_mcp"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "leave_mcp"),
        port=int(os.environ.get("DB_PORT", "3306")),
    )

# -------------------------------
# Name matching utilities
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
        if Levenshtein:
            lev_sim = 1 - (Levenshtein.distance(name1_norm, name2_norm) / max(len(name1_norm), len(name2_norm), 1))
        else:
            lev_sim = SequenceMatcher(None, name1_norm, name2_norm).ratio()
        seq_sim = SequenceMatcher(None, name1_norm, name2_norm).ratio()
        return lev_sim * 0.6 + seq_sim * 0.4

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
                scores.append((first_score + last_score)/2)
            best_score = max(scores)
            if best_score >= threshold:
                matches.append({'employee': emp, 'score': best_score, 'match_type': 'fuzzy'})
        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches

# -------------------------------
# Employee fetch with optional fuzzy search
# -------------------------------
def fetch_employees_ai(search_term: str = None, emp_id: int = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if emp_id:
            cursor.execute("SELECT * FROM employee WHERE employee_id=%s", (emp_id,))
        elif search_term:
            cursor.execute("""
                SELECT * FROM employee
                WHERE first_name LIKE %s OR last_name LIKE %s OR CONCAT(first_name,' ',last_name) LIKE %s
            """, (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%"))
        else:
            return []
        rows = cursor.fetchall()
        if search_term and not rows:
            cursor.execute("SELECT * FROM employee WHERE status='Active'")
            all_employees = cursor.fetchall()
            fuzzy_matches = NameMatcher.fuzzy_match_employee(search_term, all_employees)
            rows = [m['employee'] for m in fuzzy_matches[:5]]
        return rows
    finally:
        cursor.close()
        conn.close()

# -------------------------------
# Department helper
# -------------------------------
def get_department_name(dept_id: int) -> str:
    if not dept_id:
        return "Unknown"
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT dept_name FROM department WHERE dept_id=%s", (dept_id,))
        result = cursor.fetchone()
        return result[0] if result else "Unknown"
    finally:
        cursor.close()
        conn.close()

# -------------------------------
# Format employee options
# -------------------------------
def format_employee_options(employees: List[Dict[str, Any]]) -> str:
    options = []
    for i, emp in enumerate(employees, 1):
        dept_name = get_department_name(emp.get('dept_id'))
        option = f"{i}. 👤 {emp.get('first_name')} {emp.get('last_name')} | 🏢 {dept_name} | 💼 {emp.get('job_title')}"
        options.append(option)
    return "\n".join(options)

# -------------------------------
# Resolve employee
# -------------------------------
def resolve_employee_ai(search_name: str, additional_context: str = None) -> Dict[str, Any]:
    employees = fetch_employees_ai(search_term=search_name)
    if not employees:
        return {'status':'not_found','message':f"No employees found matching '{search_name}'"}
    if len(employees) == 1:
        return {'status':'resolved','employee':employees[0]}
    if additional_context:
        context_lower = additional_context.lower()
        filtered = []
        for emp in employees:
            dept_name = get_department_name(emp.get('dept_id')).lower()
            job_title = (emp.get('job_title') or '').lower()
            email = (emp.get('email') or '').lower()
            last_name = (emp.get('last_name','')).lower()
            if context_lower in dept_name or context_lower in job_title or context_lower in email or context_lower==last_name:
                filtered.append(emp)
        if len(filtered) == 1:
            return {'status':'resolved','employee':filtered[0]}
    return {'status':'ambiguous','employees':employees,'message':f"Found {len(employees)} employees. Please specify:"}

# -------------------------------
# MCP Tools
# -------------------------------
@mcp.tool()
def get_leave_balance(name: str, additional_context: Optional[str]=None) -> str:
    resolution = resolve_employee_ai(name, additional_context)
    if resolution['status']=='not_found':
        return f"❌ No employee found matching '{name}'."
    if resolution['status']=='ambiguous':
        return f"🔍 {resolution['message']}\n\n{format_employee_options(resolution['employees'])}"

    emp = resolution['employee']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT balance FROM leave_balance WHERE employee_id=%s", (emp['employee_id'],))
        result = cursor.fetchone()
        balance = result['balance'] if result else 0
        dept_name = get_department_name(emp.get('dept_id'))
        return f"✅ **{emp['first_name']} {emp['last_name']}** | 🏢 {dept_name} | 💼 {emp.get('job_title')} | 📊 Leave Balance: {balance} days"
    finally:
        cursor.close()
        conn.close()

@mcp.tool()
def apply_leave_ai(employee_query: str, leave_dates: List[str], leave_type: str="Annual", reason: str="", additional_context: Optional[str]=None) -> str:
    resolution = resolve_employee_ai(employee_query, additional_context)
    if resolution['status']=='not_found':
        return f"❌ No employee found matching '{employee_query}'."
    if resolution['status']=='ambiguous':
        return f"🔍 Multiple employees found. Please specify:\n\n{format_employee_options(resolution['employees'])}"

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

@mcp.tool()
def smart_employee_search(search_query: str, search_type: str="auto") -> str:
    query_lower = search_query.lower().strip()
    name_part, dept_part = query_lower, None
    if "from" in query_lower:
        parts = query_lower.split(" from ")
        name_part = parts[0].strip()
        dept_part = parts[1].strip() if len(parts)>1 else None
    elif "in" in query_lower:
        parts = query_lower.split(" in ")
        name_part = parts[0].strip()
        dept_part = parts[1].strip() if len(parts)>1 else None

    resolution = resolve_employee_ai(name_part, dept_part)
    if resolution['status']=='not_found':
        return f"❌ No employees found matching '{search_query}'"
    if resolution['status']=='ambiguous':
        return f"🔍 Multiple matches:\n\n{format_employee_options(resolution['employees'])}"
    emp = resolution['employee']
    dept_name = get_department_name(emp.get('dept_id'))
    return f"✅ Match Found! 👤 {emp['first_name']} {emp['last_name']} | 🏢 {dept_name} | 💼 {emp.get('job_title')} | 📧 {emp.get('email')}"

@mcp.resource("ai_assistant://{query}")
def ai_assistant_help(query: str) -> str:
    return """
🤖 **AI-Powered Leave Management Assistant**
I can help you with:
- Search employees: "Find John Smith", "Search Priya in Engineering"
- Leave balance: "Get leave balance for John"
- Apply leave: "Apply leave for Smith"
"""

# -------------------------------
# Health check route
# -------------------------------
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

# -------------------------------
# Run MCP server
# -------------------------------
if __name__=="__main__":
    if Levenshtein is None:
        print("⚠️ python-levenshtein not installed. Fuzzy matching may be less accurate.")
    transport = os.environ.get("MCP_TRANSPORT","streamable-http")
    host = os.environ.get("MCP_HOST","0.0.0.0")
    port = int(os.environ.get("PORT","8080"))
    mcp.run(transport=transport, host=host, port=port)
