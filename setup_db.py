import os

import pymysql

conn = pymysql.connect(
    host=os.environ.get("RDS_HOST"),
    user=os.environ.get("RDS_USER"),
    password=os.environ.get("RDS_PASSWORD"),
    port=3306,
)

cursor = conn.cursor()

#create database
cursor.execute("CREATE DATABASE IF NOT EXISTS teem_planningagent;")
cursor.execute("USE teem_planningagent;")


cursor.execute("SHOW DATABASES")
print("-----databases-----")
for (db,) in cursor.fetchall():
    print(db)
#cursor.execute("DROP DATABASE desired_database")

cursor.execute("SHOW TABLES")
print("-----tables-----")
for (table,) in cursor.fetchall():
    print(table)
cursor.execute("DROP TABLE hypothesis_variable_table")
cursor.execute("DROP TABLE hypothesis_table")
cursor.execute("DROP TABLE variable_table")
cursor.execute("DROP TABLE chat_table")
cursor.execute("DROP TABLE user_table")

#user data table
cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_table (
        user_id INT AUTO_INCREMENT PRIMARY KEY,
        
        email VARCHAR(50) UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role VARCHAR(50),
        name VARCHAR(50) NOT NULL,
        class_section VARCHAR(50) NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
""")
#variable table
cursor.execute("""
    CREATE TABLE IF NOT EXISTS variable_table (
        variable_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,

        variable TEXT,
        variable_unit TEXT,
        collection_method TEXT,
        goal TEXT,
        variable_type TEXT,

        FOREIGN KEY (user_id)
            REFERENCES user_table(user_id)
            ON DELETE CASCADE
    );
""")
#hypothesis table
cursor.execute("""
    CREATE TABLE IF NOT EXISTS hypothesis_table (
        hypothesis_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,

        hypothesis TEXT,
        evidence TEXT,
        study_type TEXT,
        evidence_strength INT,

        FOREIGN KEY (user_id)
            REFERENCES user_table(user_id)
            ON DELETE CASCADE
    );
""")

#junction table
cursor.execute("""
    CREATE TABLE IF NOT EXISTS hypothesis_variable_table (
        hypothesis_id INT NOT NULL,
        variable_id INT NOT NULL,

        PRIMARY KEY (hypothesis_id, variable_id),

        FOREIGN KEY (hypothesis_id)
            REFERENCES hypothesis_table(hypothesis_id)
            ON DELETE CASCADE,
        FOREIGN KEY (variable_id)
            REFERENCES variable_table(variable_id)
            ON DELETE CASCADE
    );
""")
#transactional table for normal chatting
cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_table (
        transaction_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,

        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        module VARCHAR(50),
        user_message TEXT,
        reply TEXT,
        revision BOOL,
        hide_from_user BOOL,

        FOREIGN KEY (user_id)
            REFERENCES user_table(user_id)
            ON DELETE CASCADE
    );
""")


cursor.execute("SHOW DATABASES")
print("-----databases-----")
for (db,) in cursor.fetchall():
    print(db)

cursor.execute("SHOW TABLES")
print("-----tables-----")
for (table,) in cursor.fetchall():
    print(table)

def get_db():
    return pymysql.connect(
        host=os.environ.get("RDS_HOST"),
        user=os.environ.get("RDS_USER"),
        password=os.environ.get("RDS_PASSWORD"),
        database="teem_planningagent",
        port=3306,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )

connection = get_db()
try:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT IGNORE INTO user_table (email, password, name, class_section) VALUES (%s, %s, %s, %s)", ("admin", "123", "admin", "none")
        )
        connection.commit()
finally:
    connection.close()

conn.commit()
cursor.close()
conn.close()
print("Database setup complete.")