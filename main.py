# main.py
import os
import re
import urllib.parse
from typing import List, Optional, Dict, Any
from difflib import SequenceMatcher

import mysql.connector
from fastmcp import FastMCP

try:
    import Levenshtein
except ImportError:
    Levenshtein = None

from starlette.requests import Request
from starlette.responses import PlainTextResponse

# -------------------------------
# MCP Server
# -------------------------------
mcp = FastMCP("LeaveManager")

# -------------------------------
# MySQL Connection
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
        host=os.environ.get("DB_HOST","103.174.10.72"),
        user=os.environ.get("DB_USER","leave_mcp"),
        password=os.environ.get("DB_PASSWORD","PY@4rjQu%ha0byc7"),
        database=os.environ.get("DB_NAME","leave_mcp"),
        port=int(os.environ.get("DB_PORT",3306))
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
            lev_sim = 1 - Levenshtein.distance(n1, n2)/max(len(n1), len(n2), 1)
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
# Fetch Employees by Name
# -------------------------------
def fetch_employees_by_name(name: str) -> List[Dict[str,Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT * FROM employee 
            WHERE first_name LIKE %s OR last_name LIKE %s OR CONCAT(first_name,' ',last_name) LIKE %s
        """, (f"%{name}%", f"%{name}%", f"%{name}%"))
        rows = cursor.fetchall()
        if not rows:
            cursor.execute("SELECT * FROM employee WHERE status='Active'")
            all_emps = cursor.fetchall()
            rows = NameMatcher.fuzzy_match_employee(name, all_emps)[:5]
        return rows
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
        options.append(f"{i}. {emp['first_name']} {emp['last_name']} | {emp.get('email')} | {emp.get('job_title')} | {dept}")
    return "\n".join(options)

# -------------------------------
# Resolve Employee by Name
# -------------------------------
def resolve_employee(name: str, context: Optional[str]=None) -> Dict[str,Any]:
    emps = fetch_employees_by_name(name)
    if not emps:
        return {'status':'not_found'}
    if len(emps) == 1:
        return {'status':'resolved', 'employee': emps[0]}
    if context:
        filtered = [e for e in emps if context.lower() in (e.get('email','').lower() + get_department_name(e.get('dept_id')).lower())]
        if len(filtered) == 1:
            return {'status':'resolved','employee':filtered[0]}
        if filtered:
            emps = filtered
    return {'status':'ambiguous', 'employees': emps}

# -------------------------------
# MCP Tools (Name Based)
# -------------------------------
@mcp.tool()
def get_leave_balance(name: str, context: Optional[str]=None) -> str:
    res = resolve_employee(name, context)
    if res['status']=='not_found':
        return f"❌ No employee found with name '{name}'"
    if res['status']=='ambiguous':
        return f"⚠ Multiple matches:\n{format_employee_options(res['employees'])}"
    emp = res['employee']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT balance FROM leave_balance WHERE employee_id=%s", (emp['employee_id'],))
        bal = cursor.fetchone()
        return f"✅ {emp['first_name']} {emp['last_name']} | Leave Balance: {bal['balance'] if bal else 'N/A'} days"
    finally:
        cursor.close()
        conn.close()

@mcp.tool()
def apply_leave(name: str, leave_dates: List[str], context: Optional[str]=None) -> str:
    res = resolve_employee(name, context)
    if res['status']=='not_found':
        return f"❌ No employee found with name '{name}'"
    if res['status']=='ambiguous':
        return f"⚠ Multiple matches:\n{format_employee_options(res['employees'])}"
    emp = res['employee']
    leave_str = ",".join(leave_dates)
    return f"✅ Leave application prepared for {emp['first_name']} {emp['last_name']} | Dates: {leave_str}"

@mcp.tool()
def smart_search(name: str) -> str:
    res = resolve_employee(name)
    if res['status']=='not_found':
        return "❌ No employee found."
    if res['status']=='ambiguous':
        return f"🔍 Multiple matches:\n{format_employee_options(res['employees'])}"
    emp = res['employee']
    return f"✅ Match Found: {emp['first_name']} {emp['last_name']} | Dept: {get_department_name(emp.get('dept_id'))} | Role: {emp.get('job_title')}"

# -------------------------------
# AI Assistant
# -------------------------------
@mcp.resource("ai_assistant://{query}")
def ai_assistant(query:str) -> str:
    return """
🤖 Leave Assistant
Commands:

🔍 Search Employee:
- "Find John Smith"

📊 Leave Management:
- "Get leave balance for Priya"
- "Apply leave for John" 
"""

# -------------------------------
# Health Check
# -------------------------------
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request):
    return PlainTextResponse("OK")

# -------------------------------
# Run MCP
# -------------------------------
if __name__=="__main__":
    if Levenshtein is None:
        print("⚠ Warning: python-levenshtein not installed. Fuzzy matching may be lower.")
    transport = os.environ.get("MCP_TRANSPORT","streamable-http")
    host = os.environ.get("MCP_HOST","0.0.0.0")
    port = int(os.environ.get("PORT",8080))
    mcp.run(transport=transport, host=host, port=port)
