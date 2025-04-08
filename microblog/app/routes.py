from app import app
from app.forms import LoginForm, RegistrationForm, EditProfileForm, EmptyForm, PostForm, ResetPasswordRequestForm, ResetPasswordForm, EditPostForm
from flask import render_template, flash, redirect, url_for, request, abort, send_file, render_template_string
from flask_login import current_user, login_user, logout_user, login_required
from urllib.parse import urlsplit
import sqlalchemy as sa
from app import db
from app.models import User, Post, followers, Voucher, Basket
from datetime import datetime, timezone
from app.email import send_password_reset_email
import re
import requests
from lxml import etree

@app.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.now(timezone.utc)
        if current_user.is_vip:
            vip_expiration = current_user.vip_expiration_date.replace(tzinfo=timezone.utc)  
            if vip_expiration < datetime.now(timezone.utc):
                current_user.is_vip = False
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
        return redirect(url_for("index"))
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
    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', q):
        current_user.email = q
        db.session.commit()
        return redirect(url_for('user', username=current_user.username))
    else:
        return redirect(url_for('index'))

allowed_url = "https://jennet-better-anchovy.ngrok-free.app"
@app.route("/check", methods=["GET", "POST"])
def check():
    if request.method == 'POST':
        user_url = request.form['user_url']
        # if not allowed_url.startswith(user_url):
        #     abort(403)
        requests.get(user_url).text
    # path = request.args.get('path')
    # if path:
    #     response = requests.get("http://" + path)
    #     # return response.text
    return render_template('check.html')

@app.route('/admin')
def admin():
    form = EmptyForm()
    if request.remote_addr not in ['127.0.0.1', '::1']:
        abort(403)
    user = db.session.scalars(sa.select(User)).all()
    return render_template("admin.html", users=user, form=form)

@app.route("/whatsmyip", methods=["GET"])
def whats_my_ip():
    headers = request.headers
    print(headers)
    return str(headers) + request.remote_addr

@app.route('/checkstock', methods=['GET', 'POST'])
def check_stock():
    if request.method == 'POST':
        dtd = """<?xml version="1.0" encoding="UTF-8"?>
                <!DOCTYPE formData [
                <!ELEMENT formData (fruit)>
                <!ELEMENT fruit (#PCDATA)>
                ]>""".encode()
        xml_data = dtd + request.data
        try:
            parser = etree.XMLParser(dtd_validation=False, load_dtd=False, no_network=False, resolve_entities=True)
            root = etree.fromstring(xml_data, parser=parser)
            tree = etree.ElementTree(root)
            tree.xinclude()
            fruit = root.find("fruit").text
            print(etree.tostring(tree, pretty_print=True).decode())
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
        except etree.XMLSyntaxError as e:
            message = f"XML parsing error: {str(e)}"
        except Exception as e:
            message = f"An error occurred: {str(e)}"

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
        if not voucher_code:
            flash('Voucher code is required!', 'danger')

        # Look up the voucher by its code
        voucher = db.session.scalar(sa.select(Voucher).where(Voucher.code == voucher_code))

        if not voucher:
            flash('Voucher code not found!', 'warning')
            return redirect(url_for('index'))

        # Check if the voucher is already redeemed
        if voucher.redeemed:
            flash('This voucher has already been redeemed!', 'danger')
        else: 
            # Redeem the voucher: Update the voucher and user VIP status
            try:
                voucher.redeem(current_user)
                flash(f'Voucher {voucher_code} redeemed successfully! You now have 1 month of VIP access.', 'success')
            except ValueError as e:
                flash(str(e), 'danger')
            return render_template("redeem.html", form=form)
    return render_template("redeem.html", form=form)

@app.route('/add_to_basket', methods=['GET'])
@login_required
def add_to_basket():
    time = request.args.get('duration', type=int)
    basket = db.session.scalar(sa.select(Basket).where(Basket.user_id == current_user.user_id))
    basket.duration += time
    db.session.commit
    flash('Item added to basket!')

@app.route('/confirm_order', methods=["POST"])
def confirm_order():
    user = db.session.scalar(sa.select(User).where(User.user_id == current_user.user_id))

@app.route('/greet', methods=['GET', 'POST'])
def greet():
    if request.method == 'POST':
        name = request.form['name']
        template = f"Hello, {name}!"
        return render_template_string(template)
    return '''
        <form method="POST">
            Name: <input type="text" name="name">
            <input type="submit" value="Greet">
        </form>
    '''