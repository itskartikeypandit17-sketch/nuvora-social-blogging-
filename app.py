
import os
import sqlite3
from functools import wraps
from flask import (
    Flask, request, redirect, url_for,
    session, flash, render_template_string, g
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-before-deployment")
DB = "nuvora.db"


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        bio TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS likes (
        user_id INTEGER NOT NULL,
        post_id INTEGER NOT NULL,
        UNIQUE(user_id, post_id)
    );

    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        post_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS follows (
        follower_id INTEGER NOT NULL,
        following_id INTEGER NOT NULL,
        UNIQUE(follower_id, following_id)
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        seen INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    con.commit()
    con.close()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "uid" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def notify(user_id, message):
    db().execute(
        "INSERT INTO notifications(user_id,message) VALUES(?,?)",
        (user_id, message)
    )


PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nuvora Social</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#f4f6fb;color:#20283b;
font-family:Arial,sans-serif}
header{background:#fff;padding:16px 5%;
display:flex;justify-content:space-between;align-items:center;
box-shadow:0 2px 10px #0001;position:sticky;top:0}
.logo{font-size:26px;font-weight:bold;color:#5265e8}
nav a{margin:0 7px;color:#39415b;text-decoration:none;font-size:14px}
main{max-width:850px;margin:25px auto;padding:0 14px}
.card{background:white;padding:20px;border-radius:14px;
margin-bottom:16px;box-shadow:0 3px 14px #00000009}
input,textarea{width:100%;padding:12px;border:1px solid #ddd;
border-radius:9px;margin:7px 0;font-size:15px}
textarea{min-height:100px;resize:vertical}
button,.btn{background:#5868e9;color:white;border:0;
padding:10px 16px;border-radius:8px;cursor:pointer;
text-decoration:none;display:inline-block}
.secondary{background:#edf0ff;color:#4655c5}
.muted{color:#8790a5;font-size:13px}
a{color:#5868e9}
h2{margin-top:0}
.post-title{font-size:20px}
.actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:12px}
.comment{padding:8px;background:#f5f6fb;border-radius:8px;margin-top:7px}
@media(max-width:550px){
 header{padding:13px;display:block}
 nav{margin-top:12px;line-height:2}
 main{margin-top:15px}
 .card{padding:15px}
}
</style>
</head>
<body>
<header>
<div class="logo">Nuvora.</div>
<nav>
{% if user %}
<a href="/">Home</a>
<a href="/search">Search</a>
<a href="/notifications">Notifications</a>
<a href="/messages">Chat</a>
<a href="/profile/{{user['id']}}">Profile</a>
<a href="/logout">Logout</a>
{% else %}
<a href="/login">Login</a>
<a href="/signup">Sign Up</a>
{% endif %}
</nav>
</header>
<main>
{% with messages=get_flashed_messages() %}
{% for m in messages %}
<div class="card">{{m}}</div>
{% endfor %}
{% endwith %}
""" + """{{ content|safe }}
</main>
</body>
</html>
"""


def page(content):
    user = None
    if session.get("uid"):
        user = db().execute(
            "SELECT * FROM users WHERE id=?", (session["uid"],)
        ).fetchone()
    return render_template_string(PAGE, content=content, user=user)


@app.route("/")
@login_required
def home():
    posts = db().execute("""
    SELECT posts.*, users.username,
    (SELECT COUNT(*) FROM likes WHERE post_id=posts.id) AS likes,
    (SELECT COUNT(*) FROM comments WHERE post_id=posts.id) AS comments,
    EXISTS(SELECT 1 FROM likes
    WHERE post_id=posts.id AND user_id=?) AS liked
    FROM posts JOIN users ON users.id=posts.user_id
    ORDER BY posts.id DESC
    """, (session["uid"],)).fetchall()

    content = """
    <div class="card">
    <h2>Welcome to Nuvora</h2>
    <p class="muted">Share your thoughts through articles.</p>
    <form method="post" action="/post">
    <input name="title" placeholder="Article title" maxlength="120" required>
    <textarea name="content" placeholder="Write your article..."
    maxlength="10000" required></textarea>
    <button>Publish Article</button>
    </form></div>
    """
    for p in posts:
        content += f"""
        <div class="card">
        <div class="muted">By <a href="/profile/{p['user_id']}">
        @{p['username']}</a> · {p['created_at']}</div>
        <h2 class="post-title">{escape_html(p['title'])}</h2>
        <p>{escape_html(p['content']).replace(chr(10), '<br>')}</p>
        <div class="actions">
        <form method="post" action="/like/{p['id']}">
        <button class="secondary">{'Unlike' if p['liked'] else 'Like'} · {p['likes']}</button>
        </form>
        <a class="btn secondary" href="/post/{p['id']}">Comments · {p['comments']}</a>
        </div></div>
        """
    return page(content)


def escape_html(value):
    from html import escape
    return escape(value)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        if len(username) < 3 or len(username) > 30:
            flash("Username must be 3 to 30 characters.")
        elif len(password) < 8:
            flash("Password must have at least 8 characters.")
        else:
            try:
                cur = db().execute(
                    "INSERT INTO users(username,password) VALUES(?,?)",
                    (username, generate_password_hash(password))
                )
                db().commit()
                session["uid"] = cur.lastrowid
                return redirect("/")
            except sqlite3.IntegrityError:
                flash("This username is already taken.")
    return page("""
    <div class="card"><h2>Create your account</h2>
    <form method="post">
    <input name="username" placeholder="Choose username" required>
    <input name="password" type="password" placeholder="Password (8+ characters)" required>
    <button>Sign Up</button></form>
    <p>Already registered? <a href="/login">Login</a></p></div>
    """)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        u = db().execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        if u and check_password_hash(u["password"], password):
            session.clear()
            session["uid"] = u["id"]
            return redirect("/")
        flash("Incorrect username or password.")
    return page("""
    <div class="card"><h2>Login to Nuvora</h2>
    <form method="post">
    <input name="username" placeholder="Username" required>
    <input name="password" type="password" placeholder="Password" required>
    <button>Login</button></form>
    <p>New here? <a href="/signup">Create account</a></p></div>
    """)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/post", methods=["POST"])
@login_required
def create_post():
    title = request.form.get("title", "").strip()
    body = request.form.get("content", "").strip()
    if title and body and len(title) <= 120 and len(body) <= 10000:
        db().execute(
            "INSERT INTO posts(user_id,title,content) VALUES(?,?,?)",
            (session["uid"], title, body)
        )
        db().commit()
        flash("Article published!")
    return redirect("/")


@app.route("/like/<int:post_id>", methods=["POST"])
@login_required
def like(post_id):
    con = db()
    post = con.execute(
        "SELECT user_id FROM posts WHERE id=?", (post_id,)
    ).fetchone()
    if not post:
        return redirect("/")
    existing = con.execute(
        "SELECT 1 FROM likes WHERE user_id=? AND post_id=?",
        (session["uid"], post_id)
    ).fetchone()
    if existing:
        con.execute("DELETE FROM likes WHERE user_id=? AND post_id=?",
                    (session["uid"], post_id))
    else:
        con.execute("INSERT OR IGNORE INTO likes VALUES(?,?)",
                    (session["uid"], post_id))
        if post["user_id"] != session["uid"]:
            notify(post["user_id"], "Someone liked your article.")
    con.commit()
    return redirect("/")


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
@login_required
def comments(post_id):
    con = db()
    post = con.execute("""
    SELECT posts.*,users.username FROM posts
    JOIN users ON users.id=posts.user_id WHERE posts.id=?
    """, (post_id,)).fetchone()
    if not post:
        return redirect("/")
    if request.method == "POST":
        body = request.form.get("content", "").strip()
        if body and len(body) <= 2000:
            con.execute(
                "INSERT INTO comments(user_id,post_id,content) VALUES(?,?,?)",
                (session["uid"], post_id, body)
            )
            if post["user_id"] != session["uid"]:
                notify(post["user_id"], "Someone commented on your article.")
            con.commit()
        return redirect(f"/post/{post_id}")
    rows = con.execute("""
    SELECT comments.*,users.username FROM comments
    JOIN users ON users.id=comments.user_id
    WHERE post_id=? ORDER BY comments.id DESC
    """, (post_id,)).fetchall()
    content = f"""<div class="card"><h2>{escape_html(post['title'])}</h2>
    <p class="muted">By @{escape_html(post['username'])}</p>
    <p>{escape_html(post['content'])}</p></div>
    <div class="card"><h2>Comments</h2>
    <form method="post"><textarea name="content" maxlength="2000"
    placeholder="Write a comment..." required></textarea>
    <button>Comment</button></form>"""
    for c in rows:
        content += f"""<div class="comment">
        <b>@{escape_html(c['username'])}</b><br>
        {escape_html(c['content'])}</div>"""
    return page(content + "</div>")


@app.route("/profile/<int:user_id>", methods=["GET", "POST"])
@login_required
def profile(user_id):
    con = db()
    u = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not u:
        return redirect("/")
    own = user_id == session["uid"]
    if own and request.method == "POST":
        bio = request.form.get("bio", "")[:300]
        con.execute("UPDATE users SET bio=? WHERE id=?", (bio, user_id))
        con.commit()
        return redirect(f"/profile/{user_id}")
    followers = con.execute(
        "SELECT COUNT(*) FROM follows WHERE following_id=?", (user_id,)
    ).fetchone()[0]
    following = con.execute(
        "SELECT COUNT(*) FROM follows WHERE follower_id=?", (user_id,)
    ).fetchone()[0]
    is_following = con.execute(
        "SELECT 1 FROM follows WHERE follower_id=? AND following_id=?",
        (session["uid"], user_id)
    ).fetchone()
    content = f"""<div class="card"><h2>@{escape_html(u['username'])}</h2>
    <p>{escape_html(u['bio']) or 'No bio yet.'}</p>
    <p class="muted">{followers} Followers · {following} Following</p>"""
    if own:
        content += f"""<form method="post">
        <textarea name="bio" maxlength="300"
        placeholder="Write your bio...">{escape_html(u['bio'])}</textarea>
        <button>Save Bio</button></form>"""
    elif not is_following:
        content += f"""<form method="post" action="/follow/{user_id}">
        <button>Follow</button></form>"""
    else:
        content += f"""<form method="post" action="/unfollow/{user_id}">
        <button class="secondary">Unfollow</button></form>"""
    if not own:
        content += f'<p><a class="btn" href="/chat/{user_id}">Message</a></p>'
    content += "</div>"
    posts = con.execute(
        "SELECT * FROM posts WHERE user_id=? ORDER BY id DESC", (user_id,)
    ).fetchall()
    for p in posts:
        content += f"""<div class="card"><h2>{escape_html(p['title'])}</h2>
        <p>{escape_html(p['content'])}</p>
        <a href="/post/{p['id']}">View comments</a></div>"""
    return page(content)


@app.route("/follow/<int:user_id>", methods=["POST"])
@login_required
def follow(user_id):
    if user_id != session["uid"]:
        target = db().execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if target:
            db().execute("INSERT OR IGNORE INTO follows VALUES(?,?)",
                         (session["uid"], user_id))
            notify(user_id, "Someone followed you.")
            db().commit()
    return redirect(f"/profile/{user_id}")


@app.route("/unfollow/<int:user_id>", methods=["POST"])
@login_required
def unfollow(user_id):
    db().execute("DELETE FROM follows WHERE follower_id=? AND following_id=?",
                 (session["uid"], user_id))
    db().commit()
    return redirect(f"/profile/{user_id}")


@app.route("/search")
@login_required
def search():
    q = request.args.get("q", "").strip()[:30]
    users = db().execute(
        "SELECT id,username FROM users WHERE username LIKE ? LIMIT 30",
        ("%" + q + "%",)
    ).fetchall() if q else []
    content = """<div class="card"><h2>Find people</h2>
    <form><input name="q" placeholder="Search username">
    <button>Search</button></form></div>"""
    for u in users:
        content += f"""<div class="card">
        <a href="/profile/{u['id']}">@{escape_html(u['username'])}</a>
        </div>"""
    return page(content)


@app.route("/notifications")
@login_required
def notifications():
    rows = db().execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50",
        (session["uid"],)
    ).fetchall()
    db().execute("UPDATE notifications SET seen=1 WHERE user_id=?",
                 (session["uid"],))
    db().commit()
    content = "<div class='card'><h2>Notifications</h2>"
    for n in rows:
        content += f"<p>{escape_html(n['message'])} <span class='muted'>{n['created_at']}</span></p>"
    return page(content + "</div>")


@app.route("/messages")
@login_required
def messages():
    rows = db().execute("""
    SELECT DISTINCT users.id,users.username FROM messages
    JOIN users ON users.id =
    CASE WHEN messages.sender_id=? THEN messages.receiver_id
         ELSE messages.sender_id END
    WHERE messages.sender_id=? OR messages.receiver_id=?
    """, (session["uid"], session["uid"], session["uid"])).fetchall()
    content = "<div class='card'><h2>Your Chats</h2>"
    for u in rows:
        content += f"""<p><a href="/chat/{u['id']}">
        @{escape_html(u['username'])}</a></p>"""
    return page(content + "</div>")


@app.route("/chat/<int:user_id>", methods=["GET", "POST"])
@login_required
def chat(user_id):
    con = db()
    other = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not other or user_id == session["uid"]:
        return redirect("/messages")
    if request.method == "POST":
        body = request.form.get("content", "").strip()
        if body and len(body) <= 2000:
            con.execute(
                "INSERT INTO messages(sender_id,receiver_id,content) VALUES(?,?,?)",
                (session["uid"], user_id, body)
            )
            notify(user_id, "You received a new message.")
            con.commit()
        return redirect(f"/chat/{user_id}")
    rows = con.execute("""
    SELECT * FROM messages
    WHERE (sender_id=? AND receiver_id=?)
       OR (sender_id=? AND receiver_id=?)
    ORDER BY id
    """, (session["uid"], user_id, user_id, session["uid"])).fetchall()
    content = f"<div class='card'><h2>Chat with @{escape_html(other['username'])}</h2>"
    for m in rows:
        label = "You" if m["sender_id"] == session["uid"] else escape_html(other["username"])
        content += f"""<div class="comment"><b>{label}:</b>
        {escape_html(m['content'])}
        <div class="muted">{m['created_at']}</div></div>"""
    content += f"""<form method="post">
    <textarea name="content" maxlength="2000" placeholder="Write a message..."
    required></textarea><button>Send Message</button></form>
    <p class="muted">Refresh the page to see new messages.</p></div>"""
    return page(content)


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
  
