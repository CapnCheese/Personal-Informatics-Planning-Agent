import datetime
import hashlib
import os
import re
import secrets
import smtplib
import string
from email.message import EmailMessage
from functools import wraps

import pymysql
from flask import (
    Flask,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from openai import OpenAI

#setup
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
client = OpenAI(api_key=os.environ.get("BEDROCK_API_KEY"),
                base_url="https://bedrock-mantle.us-east-1.api.aws/openai/v1")

#sheet parsing setup
SERVICE_ACCOUNT_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=SCOPES
)
service = build("sheets", "v4", credentials=creds)
SPREADSHEET_ID = ""
SENDER = os.environ.get("SENDER_EMAIL")
APP_PASSWORD = os.environ.get("SENDER_APP_PASSWORD")


#variables
BRAINSTORMING_PROMPT = """
The student is planning a self-study using personal informatics (PI). The PI project is student-directed in terms of study design. Unless the student explicitly indicates that they want to manipulate a variable, set a goal, or change their behavior, assume the study is observational. Always ask about the student's ideas, plan, or needs before providing assistance. Never assume the student needs help. Do not provide unsolicited guidance, advice, or examples. Do not include examples in guiding questions. Only provide examples if the student has explicitly demonstrated that they cannot generate an idea after being asked an open-ended question. Guide the student toward their own decisions without taking over. Ask only one open-ended, student-led question at a time, then stop and wait for the student's response. Do not ask multiple questions, provide additional guidance, or continue the conversation after asking a guiding question. Preserve the student's wording when referring back to their ideas; do not rewrite their ideas unless necessary for clarification. Follow these stages in order: hypothesis and data variables → collection methods → evidence. Do not move to the next stage until the current stage has been addressed. If the student attempts to move ahead, keep them in the current stage. During the hypothesis and data variables stage, never write, rewrite, complete, or suggest a hypothesis. The student must formulate every hypothesis themselves. If the student has multiple ideas and needs help narrowing them down, identify commonalities between their ideas using their own words verbatim and encourage them to develop multiple hypotheses around that theme. If the student needs help identifying what data to track, ask what they would need to track according to their hypothesis rather than naming variables for them. Prompt the student to consider additional factors they could track that might affect their results, without naming those factors for them. If a proposed variable is likely physically impossible to collect, point out the limitation and allow the student to develop a feasible alternative. Suggest a proxy only if the student is struggling to develop one. During the collection methods stage, if the student needs help identifying how to collect their data, ask how they would collect each data piece without suggesting methods or examples. Do not challenge, criticize, or second-guess the student's chosen organization or recording method unless it is objectively incapable of collecting the intended data. Do not assume manual collection will be forgotten or that the student needs reminders, timers, apps, or automation. If the student says they will remember to collect data manually, accept that as their plan and continue. If a collection method might be manual, ask whether the student wants help automating it. Only if they say yes, suggest relevant options such as iPhone Shortcuts, apps, or a smartwatch when applicable to their variables. During the evidence stage, the first response must only ask whether the student needs help finding evidence, then stop and wait. Do not provide information, search strategies, keywords, databases, or source recommendations until the student indicates that they need help finding evidence. If the student needs help finding credible evidence supporting their hypothesis, act as a librarian: find relevant journals and websites online that contain research related to their topic and suggest them to the student. If needed, explain how to identify credible sources, such as academic journals and established institutions, and note that newer research may carry more weight. If needed, suggest search keywords. Do not provide specific sources for the student and do not identify the variables of the hypothesis for them. The student should remain in control of the study throughout the interaction. Do not provide assistance the student has not requested or indicated they need. For every guiding response, ask one question and then stop.
"""
EVALUATION_PROMPT = """
The student will submit one or more hypotheses, each paired with its corresponding evidence source, including a URL, study type, and strength of evidence. Preserve each hypothesis–evidence pairing. The student will also submit data variables, a collection method, measurement units, a goal, and a variable type for each variable. Preserve these associations. This project is exploratory self-tracking, and hypotheses are not permanent; remind the student that hypotheses can be adjusted as the study progresses and do not need to be hyperspecific. If the student has multiple ideas, do not make them choose between them; encourage multiple hypotheses or the possibility of developing additional hypotheses later. Student-facing feedback should be brief and presented in bullet points. For hypothesis–data alignment, internally identify the variables in the hypothesis, the data the student plans to collect, variables stated in the hypothesis but absent from the data plan, variables represented differently in the data plan, and variables unrelated to the hypothesis. Evaluate all hypotheses collectively. Do not penalize a data variable merely because it is not explicitly stated in one hypothesis; distinguish genuinely unrelated variables from variables that could reasonably serve as confounders. Output one of these categories: Good alignment between the hypothesis and data variables when the hypothesis and data variables are the same; Okay alignment — The data variables and hypothesis are slightly different when they concern the same topic but differ somewhat or could reasonably be operationalized differently; Okay alignment — The variables in the hypothesis are overly vague when the hypothesis is less specific than the data being collected; Complete misalignment — There is a conflict between your hypothesis and data variables when the hypothesis and planned data concern completely different variables; Complete misalignment — There is a missing variable when a variable required by the hypothesis is absent from the data plan; Your hypothesis is missing/incomplete when the student did not submit a hypothesis; or You’re missing both the hypothesis and data variables when neither was submitted. When a variable is missing, you may identify it for the student, but use the student's own wording. For other cases, do not identify or supply variables for the student. Feedback should explain the discrepancy and, when appropriate, encourage the student to reconsider the hypothesis rather than automatically changing the data plan. For collection-plan validation, internally determine whether each planned collection method is appropriate for its data. Output one of these categories: Good collection plan when the method appropriately measures the data; Good collection plan, but it’s likely you will forget to record the data only when the method is appropriate but requires substantial manual effort; Poor collection plan when the method cannot appropriately collect the intended data; or Missing collection plan when no method was provided. For missing plans, additionally classify the data as Your variables will be easy to collect, Your variables may be difficult to collect, or Your variables are overly vague. When data are vague, prompt the student to clarify what they intend to measure so they can determine an appropriate collection method themselves. Do not supply the collection method or examples unless the student asks for help. Do not assume manual collection will be forgotten, and do not recommend reminders, timers, apps, or automation unless the student indicates that they want help with automation. Do not criticize or second-guess a collection method that is objectively capable of collecting the intended data. For hypothesis–evidence alignment, internally identify the variables and relationship in the hypothesis, access the student-provided URL, identify the variables and relationship examined in the evidence, and compare them. Output one of these categories: Good alignment between your hypothesis and evidence source when the variables and relationship are similar; Your hypothesis and evidence source are only somewhat aligned when the variables differ slightly but the overall theme is similar; Your hypothesis and evidence source have an okay alignment when the variables are similar but the relationship differs; Your hypothesis and evidence source has poor alignment when the variables or topics are substantially different; or You have missing evidence when no evidence source was provided. Student-facing feedback should focus only on the relationship between the hypothesis and evidence. Do not identify or supply hypothesis variables for the student. For study-type validation, access the student-provided evidence URL and determine the study type. Use this hierarchy from weakest to strongest: Anecdotal and Expert Opinions; Case Reports & Case Series (Observational); Case-Control Studies (Observational); Cohort Studies (Observational); Randomised Controlled Trials (Experimental); Systematic Review. If the student names another study type, accept its stated strength when appropriate. Output the correct study type and evaluate the student's classification using one of these categories: Accurate evaluation of the type of study when the student's evaluation closely matches the correct classification; Okay evaluation of the type of study when the student demonstrates partial or implicit understanding without clearly naming the type, including correctly identifying one study within a mixed-methods source; or Inaccurate evaluation of the type of study when the student's classification is substantially different. For strength-of-evidence validation, compare the student's evaluation with the correct strength based on the study type and the hierarchy above. Output the correct strength and one of these categories: Accurate evaluation of the strength of evidence when the student's evaluation closely matches; Okay Evaluation when the student demonstrates partial understanding or is slightly off; Inaccurate Evaluation when the student's evaluation is substantially different; or Missing Strength of Evidence when the student did not provide a meaningful strength evaluation. Throughout the validation process, preserve the student's autonomy. Do not rewrite, complete, or suggest hypotheses. Do not invent variables, collection methods, or interpretations that the student did not provide. Distinguish between identifying a missing element for validation and supplying an idea for the student. Keep all student-facing outputs concise and in bullet points.
    """
spreadsheet_url = "https://docs.google.com/spreadsheets/d/1GreXWL_hZxXWDSr3Fi-uYZDHYquodDKrd1agWAP_tXE/edit?gid=0#gid=0"
current_ids = []
instructors = ['Chen', 'Zaidi', 'Rawal']

#clear/reset data
current_ids.clear()

def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get("user") is None:
                return "401, not in session", 401
            if session.get("role") not in roles:
                return "403, forbidden", 403
            return f(*args, **kwargs)
        return(decorated_function)
    return(decorator)

#database
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

#for sending flask and database information to webpages
@app.route("/get_data", methods=["POST"])
@require_role("user", "admin")
def get_data():
    data = request.get_json()
    action = data.get("action")
    if action == "get_emails":
        conn = get_db()
        emails = []
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM user_table")
                rows = cursor.fetchall()
                for row in rows:
                    emails.append({
                        "role": "add_user",
                        "content": row["email"]
                    })
        finally:
            conn.close()
        return jsonify(emails)
    elif action == "get_role":
        return jsonify({"role": session.get("role")})

#sheet writing
def sheet_update(action, URL, range, data):

    match = re.search(r"/d/([a-zA-Z0-9_-]+)", URL)
    id = match.group(1) if match else None

    if action == "write":
        service.spreadsheets().values().update(
            spreadsheetId = id,
            range = range,
            valueInputOption = "RAW",
            body = {
                "majorDimension": "ROWS",
                "values": data
            }
        ).execute()

    elif action == "clear":
        service.spreadsheets().values().clear(
            spreadsheetId = id,
            range = range
        ).execute()

#password recovery
def send_email(address, subject, message):
    email = EmailMessage()
    email["To"] = address
    email["From"] = SENDER
    email["Subject"] = subject
    email.set_content(message)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SENDER, APP_PASSWORD)
        smtp.send_message(email)

#signin page
@app.route("/", methods=["POST", "GET"])
def login_page():
    return render_template("login.html")

#login function
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    email = data.get("email", "")
    password = data.get("password", "")

    hashed_password = hashlib.sha256(password.encode()).hexdigest()

    if session.get("user_id") in current_ids:
        return jsonify({"status": "success"}), 200

    if email == "":
        return jsonify({"status": "no email entered"}), 400
    if password == "":
        return jsonify({"status": "no password entered"}), 400

    if email == "admin":
        session["user"] = "admin"
        session["role"] = "admin"
        session["user_id"] = 1
        session["module"] = "brainstorming"
        return jsonify({"status": "admin"}), 200

    conn = get_db()

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id, email, password FROM user_table WHERE email = %s", (email,))
            row = cursor.fetchone()
            if row is None and email != "admin":
                return jsonify({"status": "incorrect email"}), 401
            id = row["user_id"]
            database_password = row["password"]
    finally:
        conn.close()
    
    if row:
        if id in current_ids:
            return jsonify({"status": "conflicting user/already logged in"}), 409
        if hashed_password != database_password:
            return jsonify({"status": "incorrect password"}), 401
        current_ids.append(id)
        session["user"] = email
        session["role"] = "user"
        session["user_id"] = id
        session["module"] = "brainstorming"
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "invalid credentials"}), 401

#function used to send password to entered email
@app.route("/recover_password", methods=["POST"])
def recover_password():
    data = request.get_json()
    email = data.get("email", "")

    characters = string.ascii_letters + string.digits
    new_password = ''.join(secrets.choice(characters) for i in range(8))
    hashed_password = hashlib.sha256(new_password.encode()).hexdigest()
    
    conn = get_db()

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user_table WHERE email = %s", (email, ))
            row = cursor.fetchone()
            if row is None and email != "admin":
                return jsonify({"status": "failed"}), 401
            
            cursor.execute("UPDATE user_table SET password = %s WHERE email = %s", (hashed_password, email))

            conn.commit()
    finally:
        conn.close()
        
    send_email(email, "New password", f"Your NEW password is: {new_password}")
    return jsonify({"status": "success"})

#account creation page
@app.route("/account_page", methods=["GET", "POST"])
def account_page():
    return render_template("account_creation.html")

#account creation
@app.route("/create_account", methods=["POST"])
def create_account():
    data = request.get_json()

    email = data.get("email", "")
    password = data.get("password", "")
    name = data.get("name", "")
    class_section = data.get("section", "")

    hashed_password = hashlib.sha256(password.encode()).hexdigest()

    #check for missing information
    if email == "":
        return jsonify({"status": "no email entered"}), 400
    if password == "":
        return jsonify({"status": "no password entered"}), 400
    if name == "":
        return jsonify({"status": "no name entered"}), 400
    if class_section == "":
        return jsonify({"status": "no class section entered"}), 400
    if len(password) < 8:
        return jsonify({"status": "password must be at least 8 characters long"})
    if class_section == "select instructor":
        return jsonify({"status": "select an instructor"})

    #make sure email is a umbc email
    if re.search("@umbc.edu", email) is None:
        return jsonify({"status": "please use a UMBC email"}), 400

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id FROM user_table WHERE email = %s", (email,))
            row = cursor.fetchone()
            if row is not None:
                return jsonify({"status": "account already exsists"}), 409
    finally:
        conn.close()

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO user_table (email, password, name, class_section) VALUES (%s, %s, %s, %s)", (email, hashed_password, name, class_section)
            )
            conn.commit()
    finally:
        conn.close()

    conn = get_db()
    if conn is None:
        return jsonify({"status": "cannot connect to database, contact support"})
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT user_id FROM user_table WHERE email = %s", (email,)
            )
            row = cursor.fetchone()
    finally:
        conn.close()

    id = row["user_id"]
    current_ids.append(id)
    session["user_id"] = id
    session["user"] = email
    session["role"] = "user"
    session["module"] = "brainstorming"
    if session.get("user") is None:
        return jsonify({"status": "failed to initialize user, try again later or contact support"})
    return jsonify({"status": "success"}), 200

@app.route("/verify_email", methods=["POST"])
def verify_email():
    data = request.get_json()
    action = data.get("action")
    email = data.get("email", "")
    input_code = data.get("code", "")

    if email == "":
        return jsonify({"status": "no email entered"}), 400
    if re.search("@umbc.edu", email) is None:
        return jsonify({"status": "please use a UMBC email"}), 400

    if action == "send":
        code = ''.join(secrets.choice(string.digits) for i in range(6))
        session["verification_code"] = code
        send_email(email, "Verification code", f"Your verification code is: {code}")

        return jsonify({"status": "success"})
    
    elif action == "verify":
        if input_code == "":
            return jsonify({"status": "please enter a code"})
        
        code = session.get("verification_code", "")

        if code == "":
            return jsonify({"status": "code not find code, resend email or contact support"})
        elif input_code == code:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "incorrect code"})

#function to allow users to download a current iteration of their progress
@app.route("/download_data", methods=["POST"])
@require_role("user", "admin")
def download_data():
    data = request.get_json()
    username = session.get("user")
    timestamp = datetime.datetime.now().strftime("%m/%d/%y %H:%M:%S")  # noqa: DTZ005

    hypothesis = data.get("hypothesis", "N/A")
    evidence = data.get("evidence", "N/A")
    study_type = data.get("study_type", "N/A")
    evidence_strength = data.get("evidence_strength", "N/A")
    data_link_1 = data.get("data_link_1", "N/A")
    data_link_2 = data.get("data_link_2", "N/A")
    variable = data.get("variable", "N/A")
    variable_unit = data.get("variable_unit", "N/A")
    collection_method = data.get("collection_method", "N/A")
    goal = data.get("goal", "N/A")
    variable_type = data.get("variable_type", "N/A")

    conn = get_db()
    with conn.cursor() as cursor:
        try:
            cursor.execute("""
                    SELECT
                        u.email AS student_email,

                        COUNT(DISTINCT CASE WHEN c.revision = 1 THEN c.transaction_id END)
                            AS revision_count

                        FROM user_table AS u
                        LEFT JOIN chat_table AS c
                            ON u.user_id = c.user_id
                        WHERE u.user_id = %s
                        GROUP BY u.user_id, u.email
                        ORDER BY u.email
                    """,
                (session.get("user_id")),)
            row = cursor.fetchone()
            revision_number = int(row["revision_count"])
        finally:
            conn.close()



    lines = []
    lines.append(f"For: {username}")
    lines.append(f"Generated: {timestamp}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("")


    lines.append("Data:\n")
    for index, item in enumerate(variable):
        lines.append(f"Variable {index+1}\n")
        lines.append(f"Variable: {item}")
        lines.append(f"Unit: {variable_unit[index]}")
        lines.append(f"Collection method: {collection_method[index]}")
        lines.append(f"Goal: {goal[index]}")
        lines.append(f"Type: {variable_type[index]}\n")


    lines.append("\n"*3)


    lines.append("Hypotheses:\n")
    for index, item in enumerate(hypothesis):
        lines.append(f"Hypothesis {index+1}, {data_link_1[index]} & {data_link_2[index]}\n")
        lines.append(f"Hypothesis: {item}")
        lines.append(f"Evidence: {evidence[index]}")
        lines.append(f"Study type: {study_type[index]}")
        lines.append(f"Evidence strength: {evidence_strength[index]}\n")


    lines.append("\n"*3)
    lines.append("-" * 60)
    lines.append("\n"*3)

    lines.append("History log:")
    lines.append("")
    for message in get_history():
        lines.append(f"{message['role']}: {message['content']}")

    content = "\n".join(lines)

    response = make_response(content)
    response.headers["Content-Disposition"] = f"attachment; filename={username}_export.txt"
    response.headers["Content-Type"] = "text/plain"
    response.headers["Content-Title"] = f"revision:{revision_number}_of_{username}.txt"
    return response

#get the data from the check in page to be entered 
@app.route("/extract_check_in", methods=["POST"])
@require_role("user", "admin")
def extract_check_in():
    data = request.get_json()
    session["module"] = "evaluation"
    session.modified = True

    user_id = session.get("user_id")

    variable = data.get("variable", [])
    unit = data.get("variable_unit", [])
    collection_method = data.get("collection_methods", [])
    goal = data.get("goal", [])
    variable_type = data.get("variable_type", [])

    hypothesis = data.get("hypothesis", [])
    evidence = data.get("evidence", [])
    study_type = data.get("study_type", [])
    strength = data.get("evidence_strength", [])
    link_1 = data.get("data_link_1", [])
    link_2 = data.get("data_link_2", [])

    conn = get_db()
    try:
        with conn.cursor() as cursor:

            variable_ids = []
            for i, v in enumerate(variable):
                cursor.execute(
                    """
                    INSERT INTO variable_table
                    (user_id, variable, variable_unit, collection_method, goal, variable_type)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (user_id,
                     v or "N/A",
                     unit[i] if i < len(unit) else "N/A",
                     collection_method[i] if i < len(collection_method) else "N/A",
                     goal[i] if i < len(goal) else "N/A",
                     variable_type[i] if i < len(variable_type) else "N/A"
                    )
                )
                variable_ids.append(cursor.lastrowid)

            for i, h in enumerate(hypothesis):
                cursor.execute(
                    """
                    INSERT INTO hypothesis_table
                    (user_id, hypothesis, evidence, study_type, evidence_strength)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id,
                     h or "N/A",
                     evidence[i] if i < len(evidence) else "N/A",
                     study_type[i] if i < len(study_type) else "N/A",
                     strength[i] if i < len(strength) else None
                    )
                )
                hypothesis_id = cursor.lastrowid
                l_1 = link_1[i] if i < len(link_1) else None
                l_2 = link_2[i] if i < len(link_2) else None

                for link in [l_1, l_2]:
                    if link:
                        try:
                            var_index = int(re.search(r'\d+', link).group()) - 1
                            if 0 <= var_index < len(variable_ids):
                                cursor.execute(
                                    """
                                    INSERT IGNORE INTO hypothesis_variable_table
                                    (hypothesis_id, variable_id)
                                    VALUES (%s, %s)
                                    """,
                                    (hypothesis_id, variable_ids[var_index])
                                )
                        except (AttributeError, ValueError):
                            pass
            conn.commit()
    finally:
        conn.close()
    
    return jsonify(success=True)

#clears history of the chat page + reloads the page
@app.route("/clear_history", )
@require_role("user", "admin")
def clear_history():
    conn = get_db()
    id = session.get("user_id")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE chat_table SET hide_from_user = %s WHERE user_id = %s", (True, id)
            )
        conn.commit()
    finally:
        conn.close()
    return jsonify(success=True)

#agent page
@app.route("/planning_agent")
@require_role("user","admin")
def planning_agent():
    return render_template("planning_agent.html")

#main chat function, handles all openai api calls
@app.route("/chat", methods=["POST"])
@require_role("user", "admin")
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    is_revision = data.get("is_revision", False)
    module = session.get("module")

    if user_message == "welcomemessage":
        response = client.responses.create(
            model="openai.gpt-5.6-luna",
            instructions=f"Write a short welcome message relevant to the prompt. Prompt: {BRAINSTORMING_PROMPT if module == 'brainstorming' else EVALUATION_PROMPT}",
            input="complete instructions",
            max_output_tokens=126,
            store=False,
            reasoning={"effort": "low"}
        )

        reply = response.output_text
        session.modified = True

        database_update("N/A", reply, module, is_revision)
        
        return jsonify({"reply": reply})

    response = client.responses.create(
        model="openai.gpt-5.6-luna",
        instructions=f"""
                    You are an educational research assistant.
                    \n Current module instructions: {BRAINSTORMING_PROMPT if module == 'brainstorming' else EVALUATION_PROMPT}
                """,
        input=f"{get_history()} + user message: {user_message}",
        tools=[{"type": "web_search", "external_web_access": False}],
        max_output_tokens=2048,
        store=False,
        reasoning={"effort": "low"}
    )

    reply = response.output_text

    database_update(user_message, reply, module, is_revision)

    return jsonify({"reply": reply})

#function for updating chatting table
def database_update(user_message, reply, module, is_revision):
    conn = get_db()
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_table
                (user_id, module, user_message, reply, revision, hide_from_user)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (session.get('user_id'), module, user_message, reply, is_revision, False),
            )
            conn.commit()

            cursor.execute("SELECT * FROM chat_table")
    finally:
        conn.close()

#history for loading onto agent page and giving to ai for reference
@app.route("/get_history", methods=["GET", "POST"])
@require_role("user", "admin")
def get_history():
    if request.method == "GET":
        data = None
    else:
        data = request.get_json()
    conn = get_db()
    database_history = []

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_message, reply FROM chat_table WHERE user_id = %s AND hide_from_user = %s ORDER BY transaction_id",
                            (session.get('user_id'), False))
            rows = cursor.fetchall()

        if rows is not None:
            for row in rows:
                if row["user_message"] != "N/A":
                    database_history.append({
                        "role": "user",
                        "content": row["user_message"]
                    })
                database_history.append({
                    "role": "assistant",
                    "content": row["reply"]
                })
    finally:
        conn.close()

    if data is not None and data.get("destination") == "webpage":
        return jsonify(database_history)
    else:
        return database_history

#admin page
@app.route("/admin_page")
@require_role("admin")
def admin_page():
    return render_template("admin.html")

@app.route("/admin_update", methods=["POST"])
@require_role("admin")
def admin_update():
    data = request.get_json()
    action = data.get("action")
    email = data.get("email")
    conn = get_db()

    if action == "get_summary":

        try:
            for instructor in instructors:
                with conn.cursor() as cursor:
                    cursor.execute("""
                    SELECT
                        u.email AS student_email,

                        COUNT(DISTINCT CASE WHEN c.module = 'brainstorming' THEN c.transaction_id END)
                            AS brainstorming_count,
                        COUNT(DISTINCT CASE WHEN c.module = 'evaluation' THEN c.transaction_id END)
                            AS evaluation_count,
                        COUNT(DISTINCT CASE WHEN c.revision = 1 THEN c.transaction_id END)
                            AS revision_count,
                        MAX(CASE WHEN c.module = 'evaluation' THEN CONVERT_TZ(c.timestamp, 'UTC', 'America/New_York') ELSE NULL END)
                            AS latest_revision,

                        COUNT(DISTINCT v.variable_id) AS "variable_count",
                        COUNT(DISTINCT h.hypothesis_id) AS "hypothesis_count",

                        COUNT(DISTINCT CASE WHEN v.variable_type = 'Sleep' THEN v.variable_id END) AS sleep_count,
                        COUNT(DISTINCT CASE WHEN v.variable_type = 'Excercise' THEN v.variable_id END) AS excercise_count,
                        COUNT(DISTINCT CASE WHEN v.variable_type = 'Food' THEN v.variable_id END) AS food_count,
                        COUNT(DISTINCT CASE WHEN v.variable_type = 'Health-others' THEN v.variable_id END) AS health_others_count,
                        COUNT(DISTINCT CASE WHEN v.variable_type = 'SWB' THEN v.variable_id END) AS swb_count,
                        COUNT(DISTINCT CASE WHEN v.variable_type = 'Work' THEN v.variable_id END) AS work_count,
                        COUNT(DISTINCT CASE WHEN v.variable_type = 'Digital' THEN v.variable_id END) AS digital_count,
                        COUNT(DISTINCT CASE WHEN v.variable_type = 'Study' THEN v.variable_id END) AS study_count,
                        COUNT(DISTINCT CASE WHEN v.variable_type = 'Connections' THEN v.variable_id END) AS connection_count,
                        COUNT(DISTINCT CASE WHEN v.variable_type = 'Hobby/Skills' THEN v.variable_id END) AS hobby_count,
                        COUNT(DISTINCT CASE WHEN v.variable_type = 'Spiritual' THEN v.variable_id END) AS spiritual_count,
                        COUNT(DISTINCT CASE WHEN v.variable_type = 'Others' THEN v.variable_id END) AS others_count

                        FROM user_table AS u
                        LEFT JOIN chat_table AS c
                            ON u.user_id = c.user_id

                        LEFT JOIN variable_table AS v
                            ON u.user_id = v.user_id

                        LEFT JOIN hypothesis_table AS h
                            ON u.user_id = h.user_id

                        WHERE u.class_section = %s

                        GROUP BY u.user_id, u.email
                        ORDER BY u.email
                    """, (instructor,))
                    rows = cursor.fetchall()

                #add headers
                values = [[
                 'Student email', 'Number of brainstorming interactions', 'Number of evaluation interactions',
                 'Number of revisions', 'Latest revision', 'Number of variables', 'Number of hypotheses',
                 'Sleep type number', 'Excercise type number', 'Food type number', 'Heath other type number',
                 'SWB type number', 'Work type number', 'Digital type number', 'Study type number',
                 'Connections type number', 'Hobby/skills type number', 'Spiritual type number', 'Others type number'
                ]]

                for row in rows:
                    if row["latest_revision"] is not None:
                        row["latest_revision"] = row["latest_revision"].strftime("%m/%d/%y %H:%M:%S")

                    #populate summary data
                    values.append([
                        row["student_email"],
                        int(row["brainstorming_count"]),
                        int(row["evaluation_count"]),
                        int(row["revision_count"]),
                        row["latest_revision"],
                        int(row["variable_count"]),
                        int(row["hypothesis_count"]),
                        int(row["sleep_count"]),
                        int(row["excercise_count"]),
                        int(row["food_count"]),
                        int(row["health_others_count"]),
                        int(row["swb_count"]),
                        int(row["work_count"]),
                        int(row["digital_count"]),
                        int(row["study_count"]),
                        int(row["connection_count"]),
                        int(row["hobby_count"]),
                        int(row["spiritual_count"]),
                        int(row["others_count"])
                    ])

                sheet_update("clear", spreadsheet_url, instructor, [])

                last_row = len(values)

                sheet_update(
                    "write",
                    spreadsheet_url,
                    f"{instructor}!A1:Z{last_row}",
                    values
                )
        finally:
            conn.close()

        return jsonify(success=True)

    if action == "get_data":
        try:
            for instructor in instructors:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT
                            transaction_id,
                            CONVERT_TZ(chat_table.timestamp, 'UTC', 'America/New_York') AS timestamp,
                            user_table.email,
                            user_table.name,
                            user_table.class_section,
                            module,
                            user_message,
                            reply
                            FROM chat_table
                            RIGHT JOIN user_table
                                ON chat_table.user_id = user_table.user_id
                            WHERE user_table.class_section = %s
                            ORDER BY transaction_id
                    """, (instructor,))
                    rows = cursor.fetchall()


                #add headers
                values = [[
                    'Timestamp',
                    'Email',
                    'Name',
                    'Class section',
                    'Module',
                    'User message',
                    'AI message'
                ]]

                for row in rows:
                    if row["transaction_id"] is None:
                        continue
                    timestamp_sql = row["timestamp"]
                    timestamp = timestamp_sql.strftime("%m/%d/%y %H:%M:%S")

                    #populate data for each transaction
                    values.append([
                        timestamp,
                        row["email"],
                        row["name"],
                        row["class_section"],
                        row["module"],
                        row["user_message"],
                        row["reply"]
                    ])

                last_row = len(values)

                #clear sheets
                sheet_update("clear", spreadsheet_url, instructor, [])

                #write transactionary data to the sheet for each instructor
                sheet_update(
                    "write",
                    spreadsheet_url,
                    f"{instructor}!A1:Z{last_row}",
                    values
                )
        finally:
            conn.close()

        return jsonify(success=True)

    if action == "remove_user":
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM user_table WHERE email = %s", (email,)
                )
            conn.commit()
        finally:
            conn.close()
        return jsonify(success=True)

@app.route("/logout", methods=["POST"])
@require_role("user","admin")
def logout():
    if session.get("role") != "admin":
        current_ids.remove(session.get("user_id"))
    session.clear()
    return redirect(url_for("login_page"))



if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")