import os
import json
import uuid
import random
import datetime
import threading
import csv
import io
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort, Response
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key_change_me")

# Always read/write JSON files from the app's directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
QUESTIONS_FILE = os.path.join(BASE_DIR, "questions.json")
SCORES_FILE = os.path.join(BASE_DIR, "scores.json")

# For safe writes
DATA_LOCK = threading.Lock()

SUBJECTS = ["Physics", "Chemistry", "Botany", "Zoology", "Mental Agility Test"]
SUBJECT_TARGETS = {
    "Physics": 50,
    "Chemistry": 50,
    "Botany": 40,
    "Zoology": 40,
    "Mental Agility Test": 20
}

# Active quizzes in memory
active_quizzes = {}


def ensure_file(path, default):
    # Create file with default content only if it doesn't exist
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2, ensure_ascii=False)


def load_json(path, default=None):
    ensure_file(path, default if default is not None else [])
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            # Surface problem clearly without wiping silently
            raise RuntimeError(f"Invalid JSON in {path}: {e}")


def save_json(path, data):
    # Atomic write to avoid corruption
    tmp = f"{path}.tmp"
    with DATA_LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)


def require_login():
    return "username" in session


def compute_remark(percentage):
    if percentage >= 85:
        return "Excellent"
    elif percentage >= 60:
        return "Good"
    else:
        return "Try Again"


def get_questions(subject=None):
    data = load_json(QUESTIONS_FILE, [])
    if subject is None or subject in ("All", "full"):
        return data
    return [q for q in data if q.get("subject") == subject]


def next_question_id():
    data = load_json(QUESTIONS_FILE, [])
    return (max((q.get("id", 0) for q in data), default=0) + 1) if data else 1


def normalize_text(s):
    return " ".join((s or "").split()).strip()


def canonical_subject(subj):
    s = (subj or "").strip().lower()
    mapping = {x.lower(): x for x in SUBJECTS}
    return mapping.get(s)


@app.route("/")
def index():
    if not require_login():
        return redirect(url_for("login"))
    return render_template("index.html",
                            username=session.get("username"),
                            subjects=SUBJECTS,
                            targets=SUBJECT_TARGETS)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        users = load_json(USERS_FILE, [])
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = next((u for u in users if u.get("username") == username), None)
        if not user or not check_password_hash(user.get("password_hash", ""), password):
            return render_template("login.html", error="Invalid username or password.")
        session["username"] = username
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        users = load_json(USERS_FILE, [])
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm", "").strip()
        if not username or not password:
            return render_template("signup.html", error="Please fill all fields.")
        if password != confirm:
            return render_template("signup.html", error="Passwords do not match.")
        if any(u.get("username") == username for u in users):
            return render_template("signup.html", error="Username already exists.")
        users.append({"username": username, "password_hash": generate_password_hash(password)})
        save_json(USERS_FILE, users)
        session["username"] = username
        return redirect(url_for("index"))
    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/quiz/<subject>")
def quiz(subject):
    if not require_login():
        return redirect(url_for("login"))
    username = session.get("username")

    # Normalize subject (supports /quiz/Full%20Test, /quiz/full, /quiz/full-test, /quiz/all)
    subj_raw = (subject or "").strip()
    subj_norm = subj_raw.lower()
    if subj_norm in ("full", "full test", "full-test", "all"):
        subj_key = "full"
        subject_display = "Full Test"
    else:
        subj_key = subj_raw
        subject_display = subj_raw

    if subj_key != "full" and subj_key not in SUBJECTS:
        abort(404)

    # Load questions
    all_questions = get_questions(None if subj_key == "full" else subj_key)

    if subj_key == "full":
        combined = []
        by_subject = {s: [q for q in all_questions if q.get("subject") == s] for s in SUBJECTS}
        for s in SUBJECTS:
            avail = by_subject.get(s, [])
            if not avail:
                continue
            target = min(SUBJECT_TARGETS.get(s, len(avail)), len(avail))
            combined.extend(random.sample(avail, target) if len(avail) >= target else avail)
        random.shuffle(combined)
        selected = combined
    else:
        target = min(SUBJECT_TARGETS.get(subj_key, len(all_questions)), len(all_questions))
        selected = random.sample(all_questions, target) if target and len(all_questions) > target else all_questions

    total_questions = len(selected)
    if total_questions == 0:
        return render_template("quiz.html",
                                username=username,
                                subject=subject_display,
                                quiz_id="",
                                total_questions=0,
                                timer_seconds=0)

    timer_seconds = total_questions * 60
    quiz_id = str(uuid.uuid4())
    active_quizzes[quiz_id] = {
        "username": username,
        "subject": subject_display,
        "question_ids": [q["id"] for q in selected],
        "start_time": datetime.datetime.utcnow().isoformat(),
        "duration": timer_seconds
    }

    return render_template("quiz.html",
                            username=username,
                            subject=subject_display,
                            quiz_id=quiz_id,
                            total_questions=total_questions,
                            timer_seconds=timer_seconds)


@app.route("/api/quiz/<quiz_id>")
def api_quiz(quiz_id):
    if not require_login():
        return jsonify({"error": "Not authenticated"}), 401
    quiz = active_quizzes.get(quiz_id)
    if not quiz:
        return jsonify({"error": "Quiz not found"}), 404
    all_questions = load_json(QUESTIONS_FILE, [])
    id_set = set(quiz["question_ids"])
    order_map = {qid: idx for idx, qid in enumerate(quiz["question_ids"])}
    sanitized = []
    for q in all_questions:
        qid = q.get("id")
        if qid in id_set:
            sanitized.append({
                "id": qid,
                "subject": q.get("subject"),
                "question": q.get("question"),
                "options": q.get("options", [])
            })
    sanitized.sort(key=lambda x: order_map.get(x["id"], 10**9))
    return jsonify({"questions": sanitized})


@app.route("/submit", methods=["POST"])
def submit_quiz():
    if not require_login():
        return jsonify({"error": "Not authenticated"}), 401
    payload = request.get_json(silent=True) or {}
    quiz_id = payload.get("quiz_id")
    answers = payload.get("answers", {})  # {str(question_id): option_text}

    quiz = active_quizzes.pop(quiz_id, None)
    if not quiz:
        return jsonify({"error": "Quiz not found or expired"}), 404

    all_questions = load_json(QUESTIONS_FILE, [])
    qmap = {q["id"]: q for q in all_questions}

    subject = quiz["subject"]
    username = session.get("username")
    details = []
    correct_count = 0
    total = len(quiz["question_ids"])

    for qid in quiz["question_ids"]:
        q = qmap.get(qid)
        if not q:
            continue
        user_ans = answers.get(str(qid))
        correct = q.get("answer")
        is_correct = (user_ans == correct)
        if is_correct:
            correct_count += 1
        details.append({
            "id": qid,
            "subject": q.get("subject"),
            "question": q.get("question"),
            "options": q.get("options", []),
            "user_answer": user_ans,
            "correct_answer": correct,
            "explanation": q.get("explanation", ""),
            "is_correct": is_correct
        })

    percentage = round((correct_count / total) * 100, 2) if total else 0.0
    remark = compute_remark(percentage)

    scores = load_json(SCORES_FILE, [])
    scores.append({
        "username": username,
        "subject": subject,
        "score": correct_count,
        "total": total,
        "percentage": percentage,
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    scores_sorted = sorted(scores, key=lambda s: (s.get("percentage", 0), s.get("score", 0)), reverse=True)
    save_json(SCORES_FILE, scores_sorted)

    session["last_result"] = {
        "username": username,
        "subject": subject,
        "score": correct_count,
        "total": total,
        "percentage": percentage,
        "remark": remark,
        "details": details
    }
    return jsonify({"ok": True, "redirect": url_for("result")})


@app.route("/result")
def result():
    if not require_login():
        return redirect(url_for("login"))
    res = session.get("last_result")
    if not res:
        return redirect(url_for("index"))
    return render_template("result.html", **res)


@app.route("/leaderboard")
def leaderboard():
    if not require_login():
        return redirect(url_for("login"))
    scores = load_json(SCORES_FILE, [])
    top10 = scores[:10]
    return render_template("leaderboard.html", scores=top10, username=session.get("username"))


# ---------------- Admin + CSV ----------------

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == "admin123":
            session["admin_auth"] = True
        else:
            return render_template("admin.html", admin_authed=False, error="Invalid admin password.")
    authed = session.get("admin_auth", False)
    return render_template("admin.html", admin_authed=authed)


def require_admin():
    if not session.get("admin_auth", False):
        abort(403)


@app.route("/api/admin/questions")
def admin_get_questions():
    require_admin()
    subject = request.args.get("subject", "All")
    data = get_questions(subject if subject in SUBJECTS else None)
    return jsonify({"questions": data})


@app.route("/admin/add_question", methods=["POST"])
def admin_add_question():
    require_admin()
    payload = request.get_json(silent=True) or {}
    question_text = (payload.get("question") or "").strip()
    subject = (payload.get("subject") or "").strip()
    options = payload.get("options") or []
    answer = (payload.get("answer") or "").strip()
    difficulty = payload.get("difficulty", "Medium")
    explanation = (payload.get("explanation") or "").strip()

    if subject not in SUBJECTS:
        return jsonify({"error": "Invalid subject"}), 400
    if not question_text or not options or len(options) != 4 or not answer:
        return jsonify({"error": "Invalid inputs"}), 400
    if answer not in options:
        return jsonify({"error": "Answer must be one of the options"}), 400

    data = load_json(QUESTIONS_FILE, [])
    new_item = {
        "id": next_question_id(),
        "subject": subject,
        "question": question_text,
        "options": options,
        "answer": answer,
        "difficulty": difficulty,
        "explanation": explanation
    }
    data.append(new_item)
    save_json(QUESTIONS_FILE, data)
    return jsonify({"ok": True, "question": new_item})


@app.route("/admin/update_question", methods=["POST"])
def admin_update_question():
    require_admin()
    payload = request.get_json(silent=True) or {}
    qid = payload.get("id")
    try:
        qid = int(qid)
    except (TypeError, ValueError):
        return jsonify({"error": "Missing or invalid id"}), 400

    data = load_json(QUESTIONS_FILE, [])
    for q in data:
        if q.get("id") == qid:
            new_subject = payload.get("subject")
            new_question = payload.get("question")
            new_options = payload.get("options")
            new_answer = payload.get("answer")
            new_difficulty = payload.get("difficulty")
            new_explanation = payload.get("explanation")

            if new_subject:
                if new_subject not in SUBJECTS:
                    return jsonify({"error": "Invalid subject"}), 400
                q["subject"] = new_subject
            if new_question:
                q["question"] = new_question
            if new_options is not None:
                if not isinstance(new_options, list) or len(new_options) != 4:
                    return jsonify({"error": "Options must have 4 items"}), 400
                q["options"] = new_options
            if new_answer:
                if new_answer not in q.get("options", []):
                    return jsonify({"error": "Answer must be one of options"}), 400
                q["answer"] = new_answer
            if new_difficulty:
                q["difficulty"] = new_difficulty
            if new_explanation is not None:
                q["explanation"] = new_explanation

            save_json(QUESTIONS_FILE, data)
            return jsonify({"ok": True})

    return jsonify({"error": "Question not found"}), 404


@app.route("/admin/delete_question", methods=["POST"])
def admin_delete_question():
    require_admin()
    payload = request.get_json(silent=True) or {}
    qid = payload.get("id")
    try:
        qid = int(qid)
    except (TypeError, ValueError):
        return jsonify({"error": "Missing or invalid id"}), 400

    data = load_json(QUESTIONS_FILE, [])
    new_data = [q for q in data if q.get("id") != qid]
    if len(new_data) == len(data):
        return jsonify({"error": "Question not found"}), 404
    save_json(QUESTIONS_FILE, new_data)
    return jsonify({"ok": True})


@app.route("/admin/csv_template")
def admin_csv_template():
    require_admin()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["subject","question","optA","optB","optC","optD","answer","difficulty","explanation"])
    writer.writerow(["Physics","Which of the following is a vector quantity?","Work","Power","Energy","Pressure","Power","Medium","Power has both magnitude and direction."])
    writer.writerow(["Chemistry","pH of a neutral solution at 25°C is:","0","7","14","1","7","Easy",""])
    csv_data = output.getvalue()
    return Response(csv_data, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=questions_template.csv"})


@app.route("/admin/upload_csv", methods=["POST"])
def admin_upload_csv():
    require_admin()
    file = request.files.get("file")
    if not file or file.filename == "":
        return jsonify({"error": "No file uploaded"}), 400
    if not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "Please upload a .csv file"}), 400

    # Read CSV (handle BOM)
    try:
        stream = io.TextIOWrapper(file.stream, encoding="utf-8-sig")
    except Exception:
        content = file.read()
        stream = io.StringIO(content.decode("utf-8-sig", errors="ignore"))

    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        return jsonify({"error": "CSV has no header row"}), 400

    data = load_json(QUESTIONS_FILE, [])
    existing_keys = set((q.get("subject","").lower(), normalize_text(q.get("question","")).lower()) for q in data)

    def pick(row, keys):
        # row keys are already case-insensitive with DictReader; still normalize
        for k in keys:
            for col in row.keys():
                if (col or "").strip().lower() == k:
                    v = row.get(col)
                    if v is not None and str(v).strip() != "":
                        return str(v).strip()
        return ""

    added = 0
    skipped = 0
    errors = []
    next_id = next_question_id()

    line_idx = 1
    for raw_row in reader:
        line_idx += 1
        row = { (k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items() }

        subj_raw = pick(row, ["subject"])
        subj = canonical_subject(subj_raw)
        if not subj:
            errors.append(f"Row {line_idx}: Invalid subject '{subj_raw}'")
            skipped += 1
            continue

        question = pick(row, ["question","ques","q"])
        optA = pick(row, ["opta","option a","a"])
        optB = pick(row, ["optb","option b","b"])
        optC = pick(row, ["optc","option c","c"])
        optD = pick(row, ["optd","option d","d"])
        answer_raw = pick(row, ["answer","ans"])
        difficulty = pick(row, ["difficulty","level"]) or "Medium"
        explanation = pick(row, ["explanation","explain","exp"])

        options = [optA, optB, optC, optD]
        if not question or any(not o for o in options) or not answer_raw:
            errors.append(f"Row {line_idx}: Missing question/options/answer")
            skipped += 1
            continue

        # Map answer (A-D or exact text)
        letters = {"a":0,"b":1,"c":2,"d":3}
        ans_index = letters.get(answer_raw.strip().lower())
        if ans_index is not None:
            answer = options[ans_index]
        else:
            matches = [o for o in options if normalize_text(o).lower() == normalize_text(answer_raw).lower()]
            if not matches:
                errors.append(f"Row {line_idx}: Answer '{answer_raw}' does not match any option")
                skipped += 1
                continue
            answer = matches[0]

        key = (subj.lower(), normalize_text(question).lower())
        if key in existing_keys:
            skipped += 1
            continue

        new_item = {
            "id": next_id,
            "subject": subj,
            "question": question,
            "options": options,
            "answer": answer,
            "difficulty": difficulty,
            "explanation": explanation
        }
        data.append(new_item)
        existing_keys.add(key)
        next_id += 1
        added += 1

    if added > 0:
        save_json(QUESTIONS_FILE, data)

    return jsonify({"ok": True, "added": added, "skipped": skipped, "errors": errors})


# -------------------------------------------------------------
# VERCEL/PRODUCTION ENTRY POINT AND INITIALIZATION
# This section runs every time the Vercel serverless function starts.
# -----------------------------------------------------------------

# 1. Initialization: Ensure required JSON data files exist on the host
# This MUST be outside the if __name__ == "__main__": block for Vercel.
ensure_file(USERS_FILE, [])
ensure_file(QUESTIONS_FILE, [])
ensure_file(SCORES_FILE, [])

# 2. Vercel Entry Point: Expose the Flask application object
# Vercel's WSGI handler looks for 'application' to execute the app.
application = app


if __name__ == "__main__":
    # This block is ONLY for local development (when you run: python app.py)
    print("App running locally...")
    print(f"USERS_FILE: {USERS_FILE}")
    print(f"QUESTIONS_FILE: {QUESTIONS_FILE}")
    print(f"SCORES_FILE: {SCORES_FILE}")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)