### Example 1.
import sqlite3

def find_user(username):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchone()
### Example 2.

def search_products(search_term):
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    query = f"SELECT * FROM products WHERE name LIKE '%{search_term}%'"
    cursor.execute(query)
    return cursor.fetchall()
