from app import app
from app.forms import LoginForm, RegistrationForm, EditProfileForm, EmptyForm, PostForm, ResetPasswordRequestForm, ResetPasswordForm, EditPostForm
from flask import render_template, flash, redirect, url_for, request, abort, send_file, render_template_string, make_response, Response
from flask_login import current_user, login_user, logout_user, login_required
from urllib.parse import urlsplit
import sqlalchemy as sa
from sqlalchemy.orm.exc import StaleDataError
from app import db
from app.models import User, Post, followers, Voucher, Basket
from datetime import datetime, timezone
from app.email import send_password_reset_email
from time import sleep
import re, requests, pickle, base64, html
from lxml import etree

@app.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.now(timezone.utc)
        if not current_user.basket:
            basket = Basket(user_id=current_user.id)
            db.session.add(basket)
            db.session.commit()
        db.session.commit()

@app.route('/', methods=["GET", "POST"])
@app.route("/index", methods=["GET", "POST"])
@login_required
def index():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(body=form.post.data, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash("Your post is now live")
        return redirect(url_for("index"))
    page = request.args.get("page", 1, type=int)
    posts = db.paginate(current_user.following_posts(), page=page, 
                        per_page=app.config["POSTS_PER_PAGE"], error_out=False)
    next_url = url_for("index", page=posts.next_num) if posts.has_next else None
    prev_url = url_for("index", page=posts.prev_num) if posts.has_prev else None
    return render_template("index.html", title="Home Page", form=form, posts=posts.items,
                           next_url = next_url, prev_url = prev_url)

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(sa.select(User).where(User.username == form.username.data))
        if user is None or not user.check_password(form.password.data):
            flash("Invalid usename or password")
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get("next")
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('index')
        pickled_user = pickle.dumps(user)
        encoded_user = base64.b64encode(pickled_user).decode('utf-8')
        response = make_response(redirect(next_page))
        response.set_cookie('user', encoded_user, httponly=True)

        return response
    return render_template("login.html", title="Sign In", form=form)

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("index"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email = form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Congratulations, you are now a registered user!")
        return redirect(url_for('login'))
    return render_template("register.html", title="Register", form=form)

@app.route("/user/<username>")
@login_required
def user(username):
    user = db.first_or_404(sa.select(User).where(User.username == username))
    page = request.args.get("page", 1, type=int)
    query = user.posts.select().order_by(Post.timestamp.desc())
    posts = db.paginate(query, page=page, per_page=app.config["POSTS_PER_PAGE"], error_out=False)
    next_url = url_for("user", username = user.username, page=posts.next_num) if posts.has_next else None
    prev_url = url_for('user', username=user.username, page=posts.prev_num) if posts.has_prev else None
    form = EmptyForm()
    return render_template("user.html", user = user, posts = posts, form = form,
                           next_url=next_url, prev_url=prev_url)

@app.route("/remove_user/<username>", methods=["POST"])
def remove_user(username):
    if request.remote_addr not in ['127.0.0.1', '::1']:
        abort(403)
    form = EmptyForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            sa.select(User).where(User.username == username))
        posts = db.session.scalars(
            sa.select(Post).where(Post.author == user)).all()
        delete_stmt = followers.delete().where(sa.or_(followers.c.follower_id == user.id, followers.c.followed_id == user.id))
        db.session.execute(delete_stmt)
        for post in posts:
            db.session.delete(post)
        db.session.delete(user)
        db.session.commit()
        flash("User deleted.")
    return redirect(url_for("admin"))

@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.about_me = form.about_me.data
        db.session.commit()
        flash("Your changes have been saved.")
        return redirect(url_for("edit_profile"))
    elif request.method == "GET":
        form.username.data = current_user.username
        form.about_me.data = current_user.about_me
    return render_template("edit_profile.html", title="Edit Profile", form=form)

@app.route("/follow/<username>", methods=["POST"])
@login_required
def follow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = db.session.scalar(sa.select(User).where(User.username == username))
        if user is None:
            flash(f"User {username} not found.")
            return redirect(url_for("index"))
        if user == current_user:
            flash("You cannot follow yourself!")
            return redirect(url_for("user", username=username))
        current_user.follow(user)
        db.session.commit()
        flash(f"You are following {username}!")
        return redirect(url_for("user", username=username))
    else:
        return redirect(url_for("index"))
    
@app.route('/unfollow/<username>', methods=['POST'])
@login_required
def unfollow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            sa.select(User).where(User.username == username))
        if user is None:
            flash(f'User {username} not found.')
            return redirect(url_for('index'))
        if user == current_user:
            flash('You cannot unfollow yourself!')
            return redirect(url_for('user', username=username))
        current_user.unfollow(user)
        db.session.commit()
        flash(f'You are not following {username}.')
        return redirect(url_for('user', username=username))
    else:
        return redirect(url_for('index'))

@app.route("/explore")
@login_required
def explore():
    page = request.args.get("page", 1, type=int)
    query = sa.select(Post).order_by(Post.timestamp.desc())
    posts = db.paginate(query, page=page, per_page=app.config["POSTS_PER_PAGE"], error_out=False)
    next_url = url_for('explore', page=posts.next_num) if posts.has_next else None
    prev_url = url_for('explore', page=posts.prev_num) if posts.has_prev else None
    return render_template("index.html", title="Explore", posts = posts.items, 
                           next_url = next_url, prev_url=prev_url)

@app.route("/reset_password_request", methods=["GET", "POST"])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = db.session.scalar(sa.select(User).where(User.email == form.email.data))
        if user:
            send_password_reset_email(user)
        flash("Check your email for the instructions to reset your password")
        return redirect(url_for("login"))
    return render_template("reset_password_request.html", title ="Reset Password", form=form)

@app.route('/reset_password_email/<token>', methods=['GET', 'POST'])
def reset_password_email(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    user = User.verify_reset_password_token(token)
    if not user:
        return redirect(url_for('index'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset.')
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form)

@app.route('/reset_password', methods=['GET', 'POST'])
@login_required
def reset_password():
    name = request.args.get("name")
    form = ResetPasswordForm()
    if form.validate_on_submit():
        current_user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset.')
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form, name=name)

@app.route("/remove_post/<id>", methods=["POST"])
@login_required
def remove_post(id):
    post = db.session.scalar(sa.select(Post).where(Post.id == id))
    if post is None:
        return redirect(url_for("index"))
    elif current_user.id != post.author.id:
        return redirect(url_for("index"))
    form = EmptyForm()
    if form.validate_on_submit():
        db.session.delete(post)
        db.session.commit()
        flash("Post removed.")
        return redirect(url_for("user", username=current_user.username))
    else:
        return redirect(url_for("index"))
    
@app.route("/edit_post/<id>", methods=["GET", "POST"])
@login_required
def edit_post(id):
    post = db.session.scalar(sa.select(Post).where(Post.id == id))
    if post is None:
        return redirect(url_for("index"))
    elif post.author.id != current_user.id:
        return redirect(url_for("index"))
    form = EditPostForm()
    if form.validate_on_submit():
        post.body = form.body.data
        db.session.commit()
        flash("Your changes have been saved.")
        return redirect(url_for("user", username = current_user.username))
    elif request.method == "GET":
        form.body.data = post.body
    return render_template("edit_post.html", title="Edit Post", form=form)

@app.route("/change_email", methods=["GET"])
@login_required
def change_email():
    q = request.args.get("q")
    if q and re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', q):
        current_user.email = q
        db.session.commit()
        return redirect(url_for('user', username=current_user.username))
    else:
        return redirect(url_for('index'))

@app.route("/check", methods=["GET", "POST"])
def check():
    if request.method == 'POST':
        user_url = request.form['user_url']
        return requests.get(user_url).text
    return render_template('check.html')

@app.route('/admin')
def admin():
    form = EmptyForm()
    if request.remote_addr not in ['127.0.0.1', '::1']:
        abort(403)
    user = db.session.scalars(sa.select(User)).all()
    return render_template("admin.html", users=user, form=form)

@app.route('/robots.txt')
def robots():
    robots_txt = """
    User-agent: *
    Disallow: /about
    Disallow: /contact
    """
    return Response(robots_txt, mimetype='text/plain')

@app.route('/about')
def about():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>About Us - FakeCorp</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                line-height: 1.6;
                margin: 0;
                padding: 0;
                background-color: #f4f4f9;
                color: #333;
            }
            header {
                background-color: #333;
                color: #fff;
                padding: 20px 0;
                text-align: center;
            }
            header h1 {
                margin: 0;
                font-size: 2.5em;
            }
            .container {
                width: 80%;
                margin: 0 auto;
                padding: 20px;
            }
            h2 {
                color: #2c3e50;
                font-size: 1.8em;
                margin-top: 40px;
            }
            p, ul {
                font-size: 1.2em;
                line-height: 1.8;
            }
            ul {
                list-style-type: none;
                padding: 0;
            }
            .team-members, .facts, .trivia {
                margin-bottom: 40px;
            }
            .team-members ul, .trivia ul {
                padding-left: 20px;
            }
            footer {
                background-color: #333;
                color: #fff;
                padding: 10px 0;
                text-align: center;
                font-size: 0.9em;
            }
        </style>
    </head>
    <body>
        <header>
            <h1>Welcome to FakeCorp!</h1>
        </header>

        <div class="container">
            <h2>Our Mission</h2>
            <p>
                At FakeCorp, we strive to revolutionize the tech industry by providing innovative solutions to everyday problems. Our team is working tirelessly to create the future, one code line at a time. We're here to empower people through technology that’s intuitive, powerful, and accessible. Oh, and did you know? We also have a strong interest in penguins. Fun fact: Penguins are excellent swimmers, but they can’t fly!
            </p>

            <h2>History of Innovation</h2>
            <p>
                FakeCorp was founded in 2009 by Max Farquhar, who, after a breakthrough in coffee brewing technology, decided to apply the same passion to the tech industry. We started with a simple idea, then evolved into a global enterprise with over 3,000 employees worldwide. From humble beginnings to a powerhouse of tech innovation, we’ve come a long way. In fact, we were the first company to develop a fully functioning 'time travel app'...though it’s still in beta.
            </p>

            <h2>Core Values</h2>
            <ul>
                <li><strong>Integrity:</strong> We believe in doing the right thing, even when no one is watching.</li>
                <li><strong>Innovation:</strong> We’re not afraid to break the mold and think outside the box.</li>
                <li><strong>Customer-Centric:</strong> Your satisfaction is our priority.</li>
                <li><strong>Muffin Mondays:</strong> Every Monday, we enjoy freshly baked muffins from around the world. They’re the highlight of the week.</li>
            </ul>

            <h2>Meet the Team</h2>
            <div class="team-members">
                <ul>
                    <li><strong>Max Farquhar (CEO & Founder):</strong> Max once attempted to build a robot that could write poetry. It only succeeded in writing obscure sonnets about socks.</li>
                    <li><strong>Jessica Young (CTO):</strong> Jessica loves coding, but did you know she also brews her own kombucha? A self-taught programming wizard with a PhD in "Overthinking".</li>
                    <li><strong>Liam Zhang (Head of Operations):</strong> Liam once traveled to 7 different countries in 24 hours just to try 7 different types of coffee. He regrets nothing.</li>
                    <li><strong>Mia Martinez (Marketing Director):</strong> Mia has a collection of over 500 different pens. You could say she’s the <em>penultimate</em> marketing professional.</li>
                    <li><strong>Jacob Hill (Lead Developer):</strong> Jacob's a coding genius, but his real claim to fame is creating a program that predicts the best time to take a nap during the workday.</li>
                </ul>
            </div>

            <h2>Did You Know?</h2>
            <div class="facts">
                <ul>
                    <li>The longest word in the English language has 189,819 letters, and it’s the full name of a protein!</li>
                    <li>A duck's quack doesn't echo. But wait, does it really not? We need a scientific study to prove it once and for all.</li>
                    <li>The Eiffel Tower can be 15 cm taller during the summer, because metal expands in the heat! So if you visit in the summer, you might see a slightly taller tower. 🤯</li>
                </ul>
            </div>

            <h2>Random Trivia</h2>
            <div class="trivia">
                <ul>
                    <li><strong>Bananas are technically berries</strong>, but strawberries are not!</li>
                    <li><strong>Octopuses have three hearts</strong>, and they use two of them to pump blood to their gills while the third pumps blood to the rest of their body.</li>
                    <li><strong>Did you know that eating ice cream</strong> in the winter has actually been proven to improve your mood? We recommend trying it next time it’s snowing!</li>
                </ul>
            </div>

            <h2>Fun Fact of the Day</h2>
            <p>
                A day on Venus is longer than a year on Venus! It takes Venus approximately 243 Earth days to complete one rotation on its axis, but only about 225 Earth days to orbit the Sun. How does that even work? 🤔
            </p>

            <h2>Our Futuristic Vision</h2>
            <p>
                We’re currently working on a highly secretive project codenamed "Project Phoenix". Let’s just say, if you think <strong>smart glasses</strong> are cool, wait until you see what we have planned. In other news, our next team retreat will be held on a cruise ship in the Mediterranean! Expect some fun team-building activities, like synchronized swimming and solving riddles underwater.
            </p>

            <h2>Testimonial Corner</h2>
            <ul>
                <li>"FakeCorp revolutionized my life by introducing me to their magical coffee machines. I have never felt more awake in my entire life!" — Customer A</li>
                <li>"I used to think the cloud was just a metaphor. Thanks to FakeCorp, I now know it’s a place where my files can <strong>live forever</strong>!" — Customer B</li>
                <li>"I once attended a FakeCorp hackathon, and let’s just say, my project ended with me creating a virtual reality time machine. Don’t ask how!" — Customer C</li>
            </ul>

            <h2>In Closing</h2>
            <p>
                Thank you for visiting FakeCorp’s About page! We promise we’ll keep innovating, keep creating, and most importantly, keep finding new and fun ways to make your day brighter. Oh, and if you’ve read this far, we’re really impressed! You clearly have an attention span that could rival that of a goldfish. But we appreciate your commitment. Stay curious, stay creative, and remember, the future is <em>totally</em> in our hands. Just don’t try to hack our coffee machines — we’ve got a great firewall for that.
            </p>

            <footer>
                <p>"Success is like a cup of coffee; it’s best enjoyed when you’re awake, motivated, and surrounded by colleagues who don’t mind discussing the most trivial things with you."</p>
            </footer>
        </div>
    </body>
    </html>
    """

@app.route('/contact')
def contact():
    contacts = [
        "Alice Miller - alice.miller@example.com",
        "Bob Johnson - bob.johnson@example.com",
        "Carol Henderson - carol.henderson@example.com",
        "David Brooks - david.brooks@example.com",
        "Eva Roberts - eva.roberts@example.com",
        "Frank Davis - frank.davis@example.com",
        "Grace Allen - grace.allen@example.com",
        "Henry O'Connor - henry.oconnor@example.com",
        "Ivy Mitchell - ivy.mitchell@example.com",
        "Jack Evans - jack.evans@example.com",
        "Karen Thompson - karen.thompson@example.com",
        "Lily White - lily.white@example.com",
        "Monica Clark - monica.clark@example.com",
        "Oscar King - oscar.king@example.com",
        "Paul Harris - paul.harris@example.com",
        "Quincy Hall - quincy.hall@example.com",
        "Rachel Lewis - rachel.lewis@example.com",
        "Sharon Wright - sharon.wright@example.com",
        "Tina Walker - tina.walker@example.com",
        "Uma Taylor - uma.taylor@example.com",
        "Victor Scott - victor.scott@example.com",
        "Walter Adams - walter.adams@example.com",
        "Xena Brown - xena.brown@example.com",
        "Yvonne Green - yvonne.green@example.com",
        "Zachary Flagman - flag_flag@example.com",
        "Abigail Parker - abigail.parker@example.com",
        "Benjamin Young - benjamin.young@example.com",
        "Carmen Perez - carmen.perez@example.com",
        "Daniel Martin - daniel.martin@example.com",
        "Elsa Foster - elsa.foster@example.com",
        "Felix Rivera - felix.rivera@example.com",
        "Georgia Cooper - georgia.cooper@example.com",
        "Harold Powell - harold.powell@example.com",
        "Irene Simmons - irene.simmons@example.com",
        "Jackie Murphy - jackie.murphy@example.com",
        "Kyle Thomas - kyle.thomas@example.com",
        "Liam Carter - liam.carter@example.com",
        "Maggie Lewis - maggie.lewis@example.com",
        "Nina Hall - nina.hall@example.com",
        "Oscar Collins - oscar.collins@example.com",
        "Paul Walker - paul.walker@example.com",
        "Quincy Allen - quincy.allen@example.com",
        "Rita Rodriguez - rita.rodriguez@example.com",
        "Sam Watson - sam.watson@example.com",
        "Tanya Brooks - tanya.brooks@example.com",
        "Ursula Murphy - ursula.murphy@example.com",
        "Vince Green - vince.green@example.com",
        "Wendy Stewart - wendy.stewart@example.com",
        "Xander Mitchell - xander.mitchell@example.com",
        "Yasmin Morgan - yasmin.morgan@example.com",
        "Zane Wright - zane.wright@example.com",
        "Adam Simmons - adam.simmons@example.com",
        "Barbara King - barbara.king@example.com",
        "Charlie Brooks - charlie.brooks@example.com",
        "Diana Mitchell - diana.mitchell@example.com",
        "Edward Hughes - edward.hughes@example.com",
        "Frances Powell - frances.powell@example.com",
        "George Wallace - george.wallace@example.com",
        "Helen Daniels - helen.daniels@example.com",
        "Isaac Carter - isaac.carter@example.com",
        "Jessica Collins - jessica.collins@example.com",
        "Keith Roberts - keith.roberts@example.com",
        "Laura Bell - laura.bell@example.com",
        "Matthew Taylor - matthew.taylor@example.com",
        "Nancy Gray - nancy.gray@example.com",
        "Oliver Young - oliver.young@example.com",
        "Paula Clark - paula.clark@example.com",
        "Quincy Mitchell - quincy.mitchell@example.com",
        "Rita White - rita.white@example.com",
        "Sam Green - sam.green@example.com",
        "Tina Rogers - tina.rogers@example.com",
        "Ursula Martinez - ursula.martinez@example.com",
        "Vince Harris - vince.harris@example.com",
        "Walter Scott - walter.scott@example.com",
        "Xena Thompson - xena.thompson@example.com",
        "Yvonne Lee - yvonne.lee@example.com",
        "Zane Fisher - zane.fisher@example.com",
        "Flag Zachary - Flag1{Nhom3_InfoDiscl}@example.com",
        "Bethany Shaw - bethany.shaw@example.com",
        "Caleb Fox - caleb.fox@example.com",
        "Diana Jordan - diana.jordan@example.com",
        "Ethan Baker - ethan.baker@example.com",
        "Fiona Morgan - fiona.morgan@example.com",
        "George Allen - george.allen@example.com",
        "Hannah Ross - hannah.ross@example.com",
        "Ian Price - ian.price@example.com",
        "Jacki Owen - jacki.owen@example.com",
        "Liam Barnes - liam.barnes@example.com",
        "Matthew Grant - matthew.grant@example.com",
        "Nancy Harris - nancy.harris@example.com",
        "Oliver Jordan - oliver.jordan@example.com",
        "Paul Scott - paul.scott@example.com",
        "Quincy Lee - quincy.lee@example.com",
        "Rita Simmons - rita.simmons@example.com",
        "Sam Martinez - sam.martinez@example.com",
        "Tina Harris - tina.harris@example.com",
        "Ursula King - ursula.king@example.com",
        "Victor Evans - victor.evans@example.com",
        "Walter Clark - walter.clark@example.com",
        "Xena Carter - xena.carter@example.com",
        "Yvonne Parker - yvonne.parker@example.com",
        "Zane Matthews - zane.matthews@example.com",
        "Aaron Flagkeeper - flagkeeper@example.com",
        "Ben Thomas - ben.thomas@example.com",
        "Carmen Wells - carmen.wells@example.com",
        "Diana Peterson - diana.peterson@example.com",
        "Edward Evans - edward.evans@example.com",
        "Felix Morris - felix.morris@example.com",
        "Gina West - gina.west@example.com",
        "Holly Baker - holly.baker@example.com",
        "Isaac Taylor - isaac.taylor@example.com",
        "Jack Adams - jack.adams@example.com",
        "Lily Johnson - lily.johnson@example.com",
        "Mark Harris - mark.harris@example.com",
        "Nina Hughes - nina.hughes@example.com",
        "Oscar Howard - oscar.howard@example.com",
        "Paul Baker - paul.baker@example.com",
        "Quincy Harris - quincy.harris@example.com",
        "Rita Jackson - rita.jackson@example.com",
        "Sam Lee - sam.lee@example.com",
        "Tina Green - tina.green@example.com",
        "Ursula Barnes - ursula.barnes@example.com",
        "Vince Wood - vince.wood@example.com",
        "Walter Scott - walter.scott@example.com",
        "Xander Green - xander.green@example.com",
        "Yasmin O'Connor - yasmin.oconnor@example.com",
        "Zachary Flag - flag_flag2@example.com",
        "Adam Collins - adam.collins@example.com",
        "Bethany Harris - bethany.harris@example.com",
        "Clara Thomas - clara.thomas@example.com",
        "Derek Fisher - derek.fisher@example.com",
        "Elsa Moore - elsa.moore@example.com",
        "Felix Taylor - felix.taylor@example.com",
        "Georgia Turner - georgia.turner@example.com",
        "Harry Scott - harry.scott@example.com",
        "Irene White - irene.white@example.com",
        "Jake Taylor - jake.taylor@example.com",
        "Kelly Clark - kelly.clark@example.com",
        "Liam Roberts - liam.roberts@example.com",
        "Mia Green - mia.green@example.com",
        "Nancy Brooks - nancy.brooks@example.com",
        "Oscar Taylor - oscar.taylor@example.com",
        "Peter Walker - peter.walker@example.com",
        "Quincy Knight - quincy.knight@example.com",
        "Rita Green - rita.green@example.com",
        "Sam Harris - sam.harris@example.com",
        "Tina Walker - tina.walker@example.com",
        "Ursula Price - ursula.price@example.com",
        "Vera Turner - vera.turner@example.com",
        "Walter Adams - walter.adams@example.com",
        "Xena Black - xena.black@example.com",
        "Yvonne Harris - yvonne.harris@example.com",
        "Zane Walker - zane.walker@example.com"
    ]

    return "<br>".join(contacts)

@app.route("/whatsmyip", methods=["GET"])
def whats_my_ip():
    headers = request.headers
    print(headers)
    return str(headers) + request.remote_addr

class SafeResolver(etree.Resolver):
    def resolve(self, url, pubid, context):
        if url == "file:///flag.txt":
            try:
                with open("/flag.txt", "r") as f:
                    return self.resolve_string(f.read(), context)
            except Exception as e:
                return self.resolve_string(f"Error: {str(e)}", context)
        else:
            return self.resolve_string("Access denied", context)

@app.route('/checkstock', methods=['GET', 'POST'])
def check_stock():
    if request.method == 'POST':
        xml_data = request.data

        parser = etree.XMLParser(load_dtd=True, resolve_entities=True, no_network=True)
        parser.resolvers.add(SafeResolver())

        try:
            root = etree.fromstring(xml_data, parser=parser)
            fruit = root.find("fruit").text
        except Exception as e:
            return f"XML parse error: {str(e)}"

        stock = {
            "apple": 10,
            "banana": 5,
            "orange": 8,
            "mango": 12,
            "grapes": 3
        }

        if fruit in stock:
            message = f"The stock for {fruit} is {stock[fruit]}."
        else:
            message = f"No information for {fruit}"
        return message
    else:
        return render_template("checkstock.html")

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        uploaded_file = request.files['file']
        if uploaded_file.filename != '':
            uploaded_file.save(uploaded_file.filename)
        return redirect(url_for('index'))
    return render_template('upload.html', title="Upload")

@app.route('/svg')
def view_svg():
    # Path to the SVG file you want to serve
    return send_file("../pic.svg", mimetype="image/svg+xml")

@app.route('/render_svg')
def render_svg():

    parser = etree.XMLParser(resolve_entities=True)
    root = etree.parse("/home/kali/microblog/app/pic.svg", parser=parser)

    return etree.tostring(root)

@app.route('/redeem_voucher', methods=['GET', 'POST'])
@login_required
def redeem_voucher():
    form = EditPostForm()
    if form.validate_on_submit():
        voucher_code = form.body.data
        try:
            with db.session.begin():
                voucher = db.session.scalar(
                    sa.select(Voucher)
                    .where(Voucher.code == voucher_code)
                )

                if not voucher or voucher.redeemed:
                    flash("Voucher is invalid or already redeemed.")
                else:
                    voucher.redeemed = True
                    voucher.user_id = current_user.id
                    db.session.flush()

                    current_user.is_vip = True
                    current_user.vip_duration += 1
                    db.session.add(current_user)

                    flash(f'Voucher {voucher_code} redeemed successfully!')

        except StaleDataError:
            db.session.rollback()
            flash("This voucher was already redeemed. Please try another.")
        except Exception as e:
            db.session.rollback()
            flash("An unexpected error occurred.")

        return render_template("redeem.html", form=form)

    return render_template("redeem.html", form=form)

@app.route('/basket', methods=['GET'])
@login_required
def basket():
    basket = db.session.scalar(sa.select(Basket).where(Basket.user_id == current_user.id))
    return render_template('basket.html', basket=basket)

@app.route('/choose_subscription', methods=['GET'])
@login_required
def choose_subscription():
    return render_template("subscription.html")

@app.route('/add_to_basket', methods=['GET'])
@login_required
def add_to_basket():
    category = request.args.get('q', type=str)
    if category not in ["Basic", "Premium"]:
        flash("Invalid item!")
        return redirect(url_for('choose_subscription'))
    try:
        with db.session.begin():
            basket = db.session.scalar(sa.select(Basket).where(Basket.user_id == current_user.id))
            basket.item = category
            db.session.flush()
            flash('Item added to basket!')
    except StaleDataError:
        db.session.rollback()
        flash("Another update occurred — try again.")
    return redirect(url_for('choose_subscription'))

@app.route('/confirm_order', methods=["GET"])
def confirm_order():
    try:
        with db.session.begin():
            basket = db.session.scalar(sa.select(Basket).where(Basket.user_id == current_user.id))
            if basket.item == "Premium":
                return render_template("confirm_order.html", message="Transaction blocked!")
            sleep(5)
            basket.item = basket.item
            db.session.flush()
    except StaleDataError:
        db.session.rollback()
        return render_template("confirm_order.html", message="Order was modified by another process. Please try again.")
    return render_template("confirm_order.html", item=basket.item)

# @app.route('/greet', methods=['GET', 'POST'])
# def greet():
#     if request.method == 'POST':
#         name = request.form['name']
#         template = f"Hello, {name}!"
#         return render_template_string(template)
#     return '''
#         <form method="POST">
#             Name: <input type="text" name="name">
#             <input type="submit" value="Greet">
#         </form>
#     '''

@app.route('/deserialize')
@login_required
def deserialize():
    data = request.cookies.get('user')
    if data:
        decoded = base64.b64decode(data)
        try:
            deserialized = pickle.loads(decoded)

            return f'Deserialized Data: {html.escape(str(deserialized))}'
        except Exception as e:
            return f'Error deserializing data: {e}'
    else:
        return 'No data parameter provided.'