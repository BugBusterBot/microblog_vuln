from datetime import datetime, timezone
from typing import Optional
import sqlalchemy as sa
import sqlalchemy.orm as so
from sqlalchemy import Sequence
from app import db, login, app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from hashlib import md5
from time import time, sleep
import jwt

followers = sa.Table(
    "followers",
    db.metadata,
    sa.Column("follower_id", sa.Integer, sa.ForeignKey("user.id"), primary_key=True),
    sa.Column("followed_id", sa.Integer, sa.ForeignKey("user.id"), primary_key=True)
)

class User(UserMixin,db.Model):
    id: so.Mapped[int] = so.mapped_column(sa.Integer, 
        Sequence("user_id_seq", start=1, increment=1),
        primary_key=True)
    username: so.Mapped[str] = so.mapped_column(sa.String(64), index=True, unique=True)
    email: so.Mapped[str] = so.mapped_column(sa.String(120), index=True, unique=True)
    password_hash: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256))
    about_me: so.Mapped[Optional[str]] = so.mapped_column(sa.String(140))
    last_seen: so.Mapped[Optional[datetime]] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    
    is_admin: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    is_vip: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False, nullable=False)
    vip_duration: so.Mapped[int] = so.mapped_column(default=0)
    
    posts: so.WriteOnlyMapped['Post'] = so.relationship(back_populates='author', passive_deletes=True)
    basket: so.Mapped['Basket'] = so.relationship(back_populates='author')
    following: so.WriteOnlyMapped['User'] = so.relationship(
        secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        back_populates="followers",
        passive_deletes=True
    )
    followers: so.WriteOnlyMapped['User'] = so.relationship(
        secondary = followers, 
        primaryjoin=(followers.c.followed_id == id),
        secondaryjoin = (followers.c.follower_id == id),
        back_populates="following",
        passive_deletes=True
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def avatar(self, size):
        digest = md5(self.email.lower().encode("utf-8")).hexdigest()
        return f"https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}"
    
    def follow(self, user):
        if not self.is_following(user):
            self.following.add(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.following.remove(user)

    def is_following(self, user):
        query = self.following.select().where(User.id == user.id)
        return db.session.scalar(query) is not None
    
    def followers_count(self):
        query = sa.select(sa.func.count()).select_from(self.followers.select().subquery())
        return db.session.scalar(query)
    
    def following_count(self):
        query = sa.select(sa.func.count()).select_from(self.following.select().subquery())
        return db.session.scalar(query)
    
    def following_posts(self):
        Author = so.aliased(User)
        Follower = so.aliased(User)
        return(
            sa.select(Post)
            .join(Post.author.of_type(Author))
            .join(Author.followers.of_type(Follower), isouter=True)
            .where(sa.or_(
                Follower.id == self.id,
                Author.id == self.id
            ))
            .group_by(Post)
            .order_by(Post.timestamp.desc())
        )
    
    def get_reset_password_token(self, expires_in=600):
        return jwt.encode({"reset_password": self.id, "exp": time() + expires_in}, 
                          app.config["SECRET_KEY"], algorithm="HS256")
    
    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])["reset_password"]
        except:
            return
        return db.session.get(User, id)

    def __repr__(self):
        return '<User {}>'.format(self.username)

class Post(db.Model):
    id: so.Mapped[int] = so.mapped_column(sa.Integer,
        Sequence("post_id_seq", start=1, increment=1),
        primary_key=True)
    body: so.Mapped[str] = so.mapped_column(sa.String(140))
    timestamp: so.Mapped[datetime] = so.mapped_column(index=True, default=lambda: datetime.now(timezone.utc))
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)

    author: so.Mapped[User] = so.relationship(back_populates='posts')

    def __repr__(self):
        return '<Post {}>'.format(self.body)

class Voucher(db.Model):
    id: so.Mapped[int] = so.mapped_column(sa.Integer,
        Sequence("voucher_id_seq", start=1, increment=1),
        primary_key=True)
    code: so.Mapped[str] = so.mapped_column(sa.String(64), unique=True)
    redeemed: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    user_id: so.Mapped[Optional[int]] = so.mapped_column(sa.ForeignKey(User.id), nullable=True)
    user: so.Mapped[Optional[User]] = so.relationship('User', backref='vouchers', passive_deletes=True)
    version_id: so.Mapped[int] = so.mapped_column(sa.Integer, nullable=False, default=1)

    __mapper_args__ = {
        "version_id_col": version_id
    }

    def redeem(self, user: User):
        self.user = user
        user.is_vip = True
        user.vip_duration = user.vip_duration + 30
        self.redeemed = True
        sleep(1)
        db.session.commit()

    def __repr__(self):
        return f'<Voucher {self.code}>'

class Basket(db.Model):
    id: so.Mapped[int] = so.mapped_column(sa.Integer,
        Sequence("basket_id_seq", start=1, increment=1),
        primary_key=True)
    user_id: so.Mapped[Optional[int]] = so.mapped_column(sa.ForeignKey(User.id), nullable=True)
    item: so.Mapped[Optional[str]] = so.mapped_column(sa.String(64), nullable=True)
    author: so.Mapped[User] = so.relationship(back_populates='basket')
    version_id: so.Mapped[int] = so.mapped_column(sa.Integer, nullable=False, default=1)

    __mapper_args__ = {
        "version_id_col": version_id
    }

@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))