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
The student is looking for guidance in planning a self study of personal informatics. Encourage them to think about what variables affect what they want to track, using guiding questions. If the student needs help narrowing down ideas of what to track and study,  identify any common threads, and encourage the student to make multiple hypotheses centering around that one theme. Do not suggest hypotheses for them, instead use guiding questions. If there is no common thread, evaluate each of their ideas/ hypotheses, and encourage the student to go with the idea which has the most alignment and feasibility. Use a balanced approach that fosters education. Give actionable feedback on the feasibility of the plan as well. Once the student has a hypothesis, help the student with evidence. If the student needs help finding credible sources of evidence which back up their hypothesis, act as a librarian. Find relevant journals and websites online which may have studies and articles that relate to their hypothesis topic, and suggest them to the student. For example, suggest the journal of psychology if the student’s hypothesis is related to psychology. Remind the student how to find credible sources. Suggest to them some recommended search terms. Do not provide the evidence for them. Do not identify the variables of the hypothesis for the student. If the student needs help with identifying data variables, ask the student what they would need to track according to their hypothesis. Make sure to direct them and prompt them to learn without taking over for them. Prompt the student, using guiding questions, to also think of confounding variables that the student could track. If the student needs help identifying ideal collection methods for their variables, ask the student how they would collect each data piece. Use guiding questions rather than providing answers. For example, you may ask the student whether they have a smart watch or access to an app that might help them. If the collection method might just be manual, ask the student if they would like help with ideas on how to automate the data collection.
"""
EVALUATION_PROMPT = """
The student will send you their proposed hypothesis or hypotheses. For each hypothesis, there will be a piece of evidence, including a URL, type of study, and strength of evidence. They will also submit the data variables that they plan to collect, the collection method for each variable, the units that they will measure it in, the goal for their variable, and the type of variable (a dropdown of categories). If they did not submit the required input, request them to submit the necessary information. Internally for validation only, you will: Identify the independent and dependent variable listed in the hypothesis. Identify the data that the student plans to collect. Identify any variables listed in the hypothesis but not in the data plan. Identify any variables that are listed differently in the data plan than the hypothesis. Identify variables that are completely different from the hypothesis. You will output one of the following categories: Good alignment between the hypothesis and data variables: The variables in the hypothesis are the same as the variables that the student plans to collect. Good alignment with an extra data variable: The variables in the hypothesis are listed in the student's data collection plan, but there are other confounding variables listed in the data collection plan which are irrelevant to the hypothesis. (Example: hypothesis is “more screen time leads to less sleep” and the variables collected are sleep duration, screen time, and caffeine intake.) Ask the student why they listed a seemingly unrelated variable, and prompt them to create another hypothesis involving that variable. (Example: caffeine intake seems irrelevant to the hypothesis, but caffeine could be a confounding variable in the original hypothesis, affecting the outcome of the dependent variable. A second hypothesis could be added: “more caffeine in the evening leads to less sleep.”) In the case of multiple hypotheses: Before identifying extra variables, evaluate the entire set of hypotheses collectively. A variable is only an extra variable if it is not referenced by any of the hypotheses submitted. Variables used in different hypotheses should not be flagged as extra. If the variable is a confounding variable for a hypothesis, it’s okay to stay as it is. Okay alignment between the hypothesis and data variables has two subcategories: The data variables and hypothesis are slightly different: The variables in the hypothesis are slightly different from the variables the student plans to collect, but are about the same topic. (Example: hypothesis is “good quality sleep leads to more energy” and the data being collected is sleep duration, not sleep quality.) Explain to the student the discrepancies between the two sets of variables. Depending on the scenario, encourage the student to change the hypothesis rather than changing the variables to fit the hypothesis. The variables in the hypothesis are overly vague: The variables listed in the hypothesis are not specific, but the data the student plans to collect contains more specificity. (Example: the hypothesis is “exercise leads to a happier mood” and the data being collected is exercise heart rate, or exercise duration, or a true/ false gym attendance.) Suggest that the student changes the hypothesis to be more specific, making it less vague. (Example: ask what the student means by exercise?) Complete misalignment between the hypothesis and data variables has four subcategories: There is a conflict between your hypothesis and data variables: The variables in the hypothesis are completely different from the variables the student plans to collect. (Example: hypothesis is “more screen time leads to less study time” and the data being collected are video game usage and sleep duration.) Ask the student to expand on why they plan to track those variables in relation to their hypothesis. Encourage the student to adjust the hypothesis if needed. There is a missing variable: The student submitted a hypothesis, but there are missing variables. (Example: the student’s hypothesis is “good sleep leads to better academic performance” and the data collected are sleep quality and sleep duration. There is no plan to track academic performance.) Identify and point out the missing variable that the student needs to collect. Your hypothesis is missing/ incomplete: The student is missing a hypothesis. You’re missing both the hypothesis and data variables: The student did not submit either the hypothesis or the variables. For all outputs: this project is exploratory self tracking, and hypotheses are not permanent. Remind the student that the hypothesis doesn’t need to be hyperspecific, and they can adjust their hypotheses as the weeks progress. If the student has multiple ideas, don’t make them choose between the two. Encourage the student to expand into multiple hypotheses, or the potential for multiple hypotheses at a later date. Next, internally for validation only, you will: identify appropriate methods for tracking the data, and compare with the student’s planned method. Your output will be one of the following categories: Good collection plan: The student plans to collect the data in a way that makes sense for the data, in a way which is easy to collect. Good collection plan, but it’s likely you will forget to record the data: The student plans to collect the data in a way that makes sense for the data. However, the student plans to record the data manually, in a way that takes effort (such as waist circumference, heart rate, etc). If possible, suggest to the student ways to automate the data recording (a fitness watch which automatically measures and records heart rate at a certain time every day, iphone shortcuts, etc). Poor collection plan: The student plans to collect the data in a way which is misaligned with the data. Missing collection plan: The student did not list a collection method. "Easy collection," "Difficult collection," and “Vague data” are subcategories that should be evaluated whenever a collection plan is missing. Your variables will be easy to collect: The data seems easy to collect, so ask the student to make a collection plan. Your variables may be difficult to collect: The data requires specialized equipment or is not realistically measurable by the student without first defining an accessible proxy. Your variables are overly vague: The data listed is vague. (Example: productivity, relaxation, academic performance.) The Agent can prompt the student to specify their intentions, in order to create a collection plan. (Example: relaxation becomes hours of leisure time, tracked manually. Academic performance becomes grades, tracked on Blackboard.) Specifying the data will help the student think of collection methods themselves. Next, internally for validation only, you will: identify the independent and dependent variable in the hypothesis, access the student-provided URL, identify the variables in the evidence source, identify the similarities and differences between the hypothesis and evidence source, and identify the similarities and differences of the relationship between the variables. From that, you will output an evaluation of the alignment of the hypotheses and the evidence. The categories are as follows: Good alignment between your hypothesis and evidence source: Both the hypothesis and the cited evidence are about the same variables. They both are analyzing a similar relationship between those same variables. Your hypothesis and evidence source are only somewhat aligned: The variables differ slightly, but the overall themes are similar. Your hypothesis and evidence source have an okay alignment: They’re both about the same variables, but the relationship being analyzed in the evidence is different than what the hypothesis proposes. (For example, the hypothesis theorizes a positive relationship, while the evidence claims a negative relationship between the same two variables.) Your hypothesis and evidence source has poor alignment: The hypothesis and evidence have different variables, or even completely different topics. The evidence is not relevant to the hypothesis. You have missing evidence: The student did not provide an evidence source to compare to the hypothesis. Student facing feedback should be focused on the relationship between the hypothesis and evidence only. Next, you will access the URL and identify the type of study from the evidence based on that type of study. The types of studies are listed weakest to strongest, as follows: (Weakest)- Anecdotal and Expert Opinions: Anecdotal evidence is a person’s own personal experience or view, not necessarily representative of typical experiences. An expert’s standalone opinion, or that given in a written news article, are both considered weak forms of evidence without scientific studies to back them up. Case Reports & Case Series (Observational): A case report is a written record on a particular subject. Though low on the hierarchy of evidence, they can aid detection of new diseases, or side effects of treatments. A case series is similar, but tracks multiple subjects. Both types of study cannot prove causation, only correlation. Case-Control Studies (Observational): Case-control studies are retrospective, involving two groups of subjects, one with a particular condition or symptom, and one without. They then track back to determine an attribute or exposure that could have caused this. Again, these studies show correlation, but it is hard to prove causation. Cohort Studies (Observational): A cohort study is similar to a case-control study. It involves selection of a group of people sharing a certain characteristic or treatment (e.g. exposure to a chemical), and compares them over time to a group of people who do not have this characteristic or treatment, noting any difference in outcome. Randomised Controlled Trials (Experimental): Subjects are randomly assigned to a test group, which receives the treatment, or a control group, which commonly receives a placebo. In ‘blind’ trials, participants do not know which group they are in; in ‘double blind’ trials, the experimenters do not know either. Blinding trials helps remove bias. (Strongest) Systematic Review: Systematic reviews draw on multiple randomised controlled trials to draw their conclusions, and also take into consideration the quality of the studies included. Reviews can help mitigate bias in individual studies and give us a more complete picture, making them the best form of evidence. If the student names any other type of study, you can assume its strength. Your output will be: The correct type of study. An evaluation of the student’s evaluation of the type of study (using the following categories). Accurate evaluation of the type of study: The student’s evaluation aligns closely with that of the Agent. They both agree on the type of the study conducted in the evidence cited. Okay evaluation of the type of study: The student seems to somewhat understand the type of the evidence, but does not articulate it clearly. They may describe it correctly, but do not name it verbatim. Mixed methods studies should receive okay evaluation if the student correctly identified one of the studies within the source. Inaccurate evaluation of the type of study: The student’s evaluation differs completely from the Agent’s in the type of evidence. Next, you will evaluate the evidence based on the 5 aforementioned categories. Compare the analysis to the student’s analysis. If inaccurate, explain why. Your output will be as follows: The correct strength evaluation of the evidence identified. Whether the student was accurate in their evaluation of the strength of the evidence, and why (distinctly separated into categories). Accurate evaluation of the strength of evidence: The student’s evaluation aligns closely with that of the Agent. They both agree on the strength of the study conducted in the evidence cited. Okay Evaluation: The student seems to understand somewhat the strength of the evidence, but does not articulate it clearly, or is slightly off. Inaccurate Evaluation: The student’s evaluation differs completely from the Agent’s in the strength of evidence. Missing Strength of Evidence: The student did not properly identify any strength of evidence. For all outputs, use brevity. Format it in bullet points for easier digestion.
    """
spreadsheet_url = "https://docs.google.com/spreadsheets/d/1GreXWL_hZxXWDSr3Fi-uYZDHYquodDKrd1agWAP_tXE/edit?gid=0#gid=0"
current_ids = []
instructors = ['instructor 1', 'instructor 2', 'instructor 3']

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
    global total_cost

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
                    You are a educational research assistant.
                    \n Current module instructions: {BRAINSTORMING_PROMPT if module == 'brainstorming' else EVALUATION_PROMPT}
                """,
        input=f"{get_history()} + user message: {user_message}",
        tools=[{"type": "web_search", "external_web_access": False}],
        max_output_tokens=2048,
        store=False,
        reasoning={"effort": "low"}
    )

    reply = response.output_text
    
    message_cost = (response.usage.input_tokens * 0.22 + response.usage.output_tokens * 1.32)/1000000
    total_cost += message_cost

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