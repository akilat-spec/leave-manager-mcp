import mysql.connector

try:
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",  # Empty password
        database="leave_db"
    )
    print("✅ Database connection successful!")
    
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    print(f"📊 Tables in database: {[table[0] for table in tables]}")
    
    cursor.close()
    conn.close()
    
except mysql.connector.Error as e:
    print(f"❌ Database connection failed: {e}")