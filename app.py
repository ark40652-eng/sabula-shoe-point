import os, re, json, uuid
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'shoeworld-secret-2026')

db_url = os.environ.get('DATABASE_URL', 'sqlite:///shoeworld.db')
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['ADMIN_USERNAME'] = os.environ.get('ADMIN_USERNAME', 'sabula')
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', '123456')
app.config['ADMIN_EMAIL'] = os.environ.get('ADMIN_EMAIL', 'hidden@sabulashoes.com')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

db = SQLAlchemy(app)


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text


# ===================== MODELS =====================

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    icon = db.Column(db.String(50), default='fa-shoe-prints')
    products = db.relationship('Product', backref='category', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Category {self.name}>'


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    discount_price = db.Column(db.Float, nullable=False)
    discount_percent = db.Column(db.String(10))
    image_url = db.Column(db.String(500))
    rating = db.Column(db.Float, default=5.0)
    reviews_count = db.Column(db.Integer, default=0)
    badge = db.Column(db.String(50), default='HOT DEAL')
    in_stock = db.Column(db.Boolean, default=True)
    featured = db.Column(db.Boolean, default=False)
    trending = db.Column(db.Boolean, default=False)
    affordable = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Product {self.name}>'


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=True)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    orders = db.relationship('Order', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    customer_name = db.Column(db.String(200), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    customer_email = db.Column(db.String(200), default='')
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Pending')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Order #{self.id}>'


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Float, nullable=False)

    product = db.relationship('Product', backref='order_items')


# ===================== CONTEXT PROCESSORS =====================

@app.context_processor
def inject_globals():
    categories = Category.query.all()
    cart = session.get('cart', [])
    cart_count = sum(item['quantity'] for item in cart)
    cart_total = 0
    cart_items = []
    for item in cart:
        product = Product.query.get(item['product_id'])
        if product:
            subtotal = product.discount_price * item['quantity']
            cart_total += subtotal
            cart_items.append({
                'product': product,
                'quantity': item['quantity'],
                'subtotal': subtotal
            })
    user = None
    if session.get('user_id'):
        user = User.query.get(session['user_id'])

    return dict(
        categories=categories,
        cart_count=cart_count,
        cart_items=cart_items,
        cart_total=cart_total,
        current_user=user
    )


@app.template_filter('format_price')
def format_price(amount):
    return f'UGX {amount:,.0f}'


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file):
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f'product_{uuid.uuid4().hex[:12]}.{ext}'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return f'uploads/{filename}'
    return ''


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ===================== ADMIN AUTH =====================

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Please login to access the admin panel.', 'warning')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


def user_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please login to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ===================== USER AUTH ROUTES =====================

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if session.get('user_id'):
        return redirect(url_for('account'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not name or not password:
            flash('Name and password are required.', 'danger')
            return render_template('signup.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('signup.html')

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('signup.html')

        if not email and not phone:
            flash('Email or Phone number is required.', 'danger')
            return render_template('signup.html')

        if email and User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('signup.html')

        if phone and User.query.filter_by(phone=phone).first():
            flash('Phone number already registered.', 'danger')
            return render_template('signup.html')

        user = User(name=name, email=email or None, phone=phone or None)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session['user_id'] = user.id
        flash(f'Welcome, {user.name}!', 'success')
        return redirect(url_for('home'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('account'))

    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter(
            db.or_(User.email == login_id, User.phone == login_id)
        ).first()

        if not user or not user.check_password(password):
            flash('Invalid credentials. Check your email/phone and password.', 'danger')
            return render_template('login.html')

        session['user_id'] = user.id
        flash(f'Welcome back, {user.name}!', 'success')
        return redirect(url_for('home'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out.', 'info')
    return redirect(url_for('home'))


@app.route('/account')
@user_required
def account():
    user = User.query.get(session['user_id'])
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    return render_template('account.html', user=user, orders=orders)


# ===================== PUBLIC ROUTES =====================

@app.route('/')
def home():
    featured = Product.query.filter_by(featured=True).order_by(Product.created_at.desc()).limit(8).all()
    discounts = Product.query.order_by(Product.discount_price.asc()).limit(6).all()
    trending = Product.query.filter_by(trending=True).order_by(Product.created_at.desc()).limit(6).all()
    affordable = Product.query.filter_by(affordable=True).order_by(Product.discount_price.asc()).limit(6).all()
    return render_template('index.html',
                           featured=featured,
                           discounts=discounts,
                           trending=trending,
                           affordable=affordable)


@app.route('/category/<string:slug>')
def category_page(slug):
    cat = Category.query.filter_by(slug=slug).first_or_404()
    products = Product.query.filter_by(category_id=cat.id).order_by(Product.created_at.desc()).all()
    return render_template('category.html', category=cat, products=products)


@app.route('/product/<string:slug>')
def product_page(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()
    related = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != product.id
    ).order_by(db.func.random()).limit(4).all()
    return render_template('product.html', product=product, related=related)


@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    results = []
    if q:
        term = f'%{q}%'
        results = Product.query.filter(
            db.or_(Product.name.ilike(term), Product.description.ilike(term))
        ).order_by(Product.created_at.desc()).all()
    return render_template('search.html', query=q, results=results)


# ===================== CART ROUTES =====================

@app.route('/cart')
def cart():
    return render_template('cart.html')


@app.route('/cart/add', methods=['POST'])
def cart_add():
    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', 1, type=int)
    product = Product.query.get_or_404(product_id)

    cart = session.get('cart', [])
    found = False
    for item in cart:
        if item['product_id'] == product_id:
            item['quantity'] += quantity
            found = True
            break
    if not found:
        cart.append({'product_id': product_id, 'quantity': quantity})
    session['cart'] = cart
    session.modified = True

    flash(f'"{product.name}" added to cart!', 'success')
    return redirect(request.referrer or url_for('home'))


@app.route('/cart/update', methods=['POST'])
def cart_update():
    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', 1, type=int)

    cart = session.get('cart', [])
    for item in cart:
        if item['product_id'] == product_id:
            if quantity <= 0:
                cart.remove(item)
            else:
                item['quantity'] = quantity
            break
    session['cart'] = cart
    session.modified = True
    return redirect(url_for('cart'))


@app.route('/cart/remove', methods=['POST'])
def cart_remove():
    product_id = request.form.get('product_id', type=int)
    cart = session.get('cart', [])
    session['cart'] = [item for item in cart if item['product_id'] != product_id]
    session.modified = True
    flash('Item removed from cart.', 'info')
    return redirect(url_for('cart'))


# ===================== CHECKOUT / ORDER =====================

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart = session.get('cart', [])
    if not cart:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('cart'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()

        if not name or not phone:
            flash('Please fill in your name and phone number.', 'danger')
            return render_template('checkout.html')

        total = 0
        items_data = []
        for item in cart:
            product = Product.query.get(item['product_id'])
            if product:
                subtotal = product.discount_price * item['quantity']
                total += subtotal
                items_data.append({
                    'product': product,
                    'quantity': item['quantity'],
                    'price': product.discount_price
                })

        order = Order(
            user_id=session.get('user_id'),
            customer_name=name,
            customer_phone=phone,
            customer_email=email,
            total_amount=total,
            status='Pending'
        )
        db.session.add(order)
        db.session.flush()

        for data in items_data:
            oi = OrderItem(
                order_id=order.id,
                product_id=data['product'].id,
                product_name=data['product'].name,
                quantity=data['quantity'],
                price=data['price']
            )
            db.session.add(oi)

        db.session.commit()
        session['cart'] = []
        session.modified = True

        flash('Order placed successfully! We will contact you shortly.', 'success')
        return redirect(url_for('confirmation', order_id=order.id))

    return render_template('checkout.html')


@app.route('/order/<int:order_id>')
def confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('confirmation.html', order=order)


@app.route('/order/whatsapp/<int:product_id>')
def order_whatsapp(product_id):
    product = Product.query.get_or_404(product_id)
    msg = f'Hello Sabula Shoe Point, I want to order this shoe: {product.name}'
    from urllib.parse import quote
    wa_url = f'https://wa.me/256709707841?text={quote(msg)}'
    return redirect(wa_url)


# ===================== ADMIN ROUTES =====================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == app.config['ADMIN_USERNAME'] and password == app.config['ADMIN_PASSWORD']:
            session['admin_logged_in'] = True
            flash('Welcome to the admin panel!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials.', 'danger')
    return render_template('admin/login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Logged out.', 'info')
    return redirect(url_for('admin_login'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    total_products = Product.query.count()
    total_orders = Order.query.count()
    total_categories = Category.query.count()
    pending_orders = Order.query.filter_by(status='Pending').count()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    return render_template('admin/dashboard.html',
                           total_products=total_products,
                           total_orders=total_orders,
                           total_categories=total_categories,
                           pending_orders=pending_orders,
                           recent_orders=recent_orders)


@app.route('/admin/products')
@admin_required
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('admin/products.html', products=products)


@app.route('/admin/products/add', methods=['GET', 'POST'])
@admin_required
def admin_product_add():
    if request.method == 'POST':
        name = request.form.get('name')
        category_id = request.form.get('category_id', type=int)
        price = request.form.get('price', type=float)
        discount_price = request.form.get('discount_price', type=float, default=0)
        badge = request.form.get('badge', 'HOT DEAL')
        rating = request.form.get('rating', 5.0, type=float)
        description = request.form.get('description', '')
        in_stock = request.form.get('in_stock') == 'on'
        featured = request.form.get('featured') == 'on'
        trending = request.form.get('trending') == 'on'
        affordable = request.form.get('affordable') == 'on'
        discount_percent = request.form.get('discount_percent', '')

        if not name or not category_id or not price:
            flash('Name, Category, and Price are required.', 'danger')
            return redirect(url_for('admin_product_add'))

        file = request.files.get('image')
        image_url = save_upload(file) if file and file.filename else ''

        if not discount_percent and discount_price and discount_price > 0:
            discount_percent = f'{int((1 - discount_price/price) * 100)}% OFF'
        elif not discount_percent:
            discount_percent = ''

        product = Product(
            name=name,
            slug=slugify(name),
            description=description,
            category_id=category_id,
            price=price,
            discount_price=discount_price or price,
            discount_percent=discount_percent,
            image_url=image_url,
            rating=rating,
            reviews_count=0,
            badge=badge,
            in_stock=in_stock,
            featured=featured,
            trending=trending,
            affordable=affordable
        )
        db.session.add(product)
        db.session.commit()
        flash(f'Product "{name}" added successfully!', 'success')
        return redirect(url_for('admin_products'))

    categories = Category.query.all()
    return render_template('admin/product_form.html', product=None, categories=categories)


@app.route('/admin/products/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_product_edit(id):
    product = Product.query.get_or_404(id)
    if request.method == 'POST':
        product.name = request.form.get('name', product.name)
        product.slug = slugify(product.name)
        product.category_id = request.form.get('category_id', product.category_id, type=int)
        product.price = request.form.get('price', product.price, type=float)
        product.discount_price = request.form.get('discount_price', product.discount_price, type=float)
        product.badge = request.form.get('badge', product.badge)
        product.rating = request.form.get('rating', product.rating, type=float)
        product.description = request.form.get('description', product.description)
        product.discount_percent = request.form.get('discount_percent', '')
        if not product.discount_percent and product.discount_price:
            product.discount_percent = f'{int((1 - product.discount_price/product.price) * 100)}% OFF'
        product.in_stock = request.form.get('in_stock') == 'on'
        product.featured = request.form.get('featured') == 'on'
        product.trending = request.form.get('trending') == 'on'
        product.affordable = request.form.get('affordable') == 'on'

        file = request.files.get('image')
        if file and file.filename:
            saved = save_upload(file)
            if saved:
                product.image_url = saved

        db.session.commit()
        flash(f'Product "{product.name}" updated!', 'success')
        return redirect(url_for('admin_products'))

    categories = Category.query.all()
    return render_template('admin/product_form.html', product=product, categories=categories)


@app.route('/admin/products/delete/<int:id>', methods=['POST'])
@admin_required
def admin_product_delete(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash(f'Product deleted.', 'info')
    return redirect(url_for('admin_products'))


@app.route('/admin/orders')
@admin_required
def admin_orders():
    status_filter = request.args.get('status', '')
    query = Order.query.order_by(Order.created_at.desc())
    if status_filter:
        query = query.filter_by(status=status_filter)
    orders = query.all()
    return render_template('admin/orders.html', orders=orders, current_status=status_filter)


@app.route('/admin/orders/<int:id>')
@admin_required
def admin_order_detail(id):
    order = Order.query.get_or_404(id)
    return render_template('admin/order_detail.html', order=order)


@app.route('/admin/orders/<int:id>/status', methods=['POST'])
@admin_required
def admin_order_status(id):
    order = Order.query.get_or_404(id)
    new_status = request.form.get('status', 'Pending')
    order.status = new_status
    db.session.commit()
    flash(f'Order #{order.id} status updated to "{new_status}".', 'success')
    return redirect(url_for('admin_order_detail', id=order.id))


# ===================== ADMIN: FORGOT PASSWORD =====================

@app.route('/admin/forgot-password', methods=['GET', 'POST'])
def admin_forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if email == app.config['ADMIN_EMAIL']:
            # In production, send email with reset link
            # For demo, show the reset page directly
            session['reset_verified'] = True
            flash('Email verified. You can now reset your password.', 'success')
            return redirect(url_for('admin_reset_password'))
        flash('Email not found. Please use the admin email.', 'danger')
    return render_template('admin/forgot_password.html')


@app.route('/admin/reset-password', methods=['GET', 'POST'])
def admin_reset_password():
    if not session.get('reset_verified'):
        flash('Please verify your email first.', 'warning')
        return redirect(url_for('admin_forgot_password'))
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if not new_password or len(new_password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
        elif new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
        else:
            app.config['ADMIN_PASSWORD'] = new_password
            session.pop('reset_verified', None)
            flash(f'Password reset successful! Your new password is: {new_password}', 'success')
            return redirect(url_for('admin_login'))
    return render_template('admin/reset_password.html')


# ===================== ADMIN: OFFERS & DISCOUNTS =====================

@app.route('/admin/offers')
@admin_required
def admin_offers():
    sort = request.args.get('sort', 'discount')
    page = request.args.get('page', 1, type=int)
    query = Product.query

    if sort == 'discount':
        query = query.order_by(Product.discount_price.asc())
    elif sort == 'percent':
        query = query.order_by(Product.discount_percent.desc())
    elif sort == 'name':
        query = query.order_by(Product.name.asc())
    else:
        query = query.order_by(Product.discount_price.asc())

    per_page = 50
    total = query.count()
    products = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page

    return render_template('admin/offers.html',
                           products=products,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           sort=sort)


@app.route('/admin/offers/update', methods=['POST'])
@admin_required
def admin_offers_update():
    product_id = request.form.get('product_id', type=int)
    product = Product.query.get_or_404(product_id)

    price = request.form.get('price', type=float)
    discount_price = request.form.get('discount_price', type=float)
    badge = request.form.get('badge', '')
    featured = request.form.get('featured') == 'on'
    trending = request.form.get('trending') == 'on'
    affordable = request.form.get('affordable') == 'on'
    in_stock = request.form.get('in_stock') == 'on'

    if price:
        product.price = price
    if discount_price is not None:
        product.discount_price = discount_price
    if badge:
        product.badge = badge
    product.featured = featured
    product.trending = trending
    product.affordable = affordable
    product.in_stock = in_stock

    if product.discount_price and product.price:
        discount_pct = int((1 - product.discount_price / product.price) * 100)
        product.discount_percent = f'{discount_pct}% OFF'

    db.session.commit()
    flash(f'"{product.name}" updated!', 'success')
    return redirect(url_for('admin_offers', page=request.form.get('page', 1)))


# ===================== SEED DATA =====================

@app.route('/seed')
def seed_categories():
    if Category.query.first():
        return 'Categories already exist. <a href="/admin">Go to Admin</a>'

    categories_data = [
        {'name': 'Sneakers', 'icon': 'fa-shoe-prints'},
        {'name': 'Formal', 'icon': 'fa-briefcase'},
        {'name': 'School', 'icon': 'fa-graduation-cap'},
        {'name': 'Boots', 'icon': 'fa-boot'},
        {'name': 'Sandals', 'icon': 'fa-socks'},
        {'name': 'Slides', 'icon': 'fa-slippers'},
        {'name': 'Heels', 'icon': 'fa-high-heel'},
        {'name': 'Sports', 'icon': 'fa-running'},
        {'name': "Men's Shoes", 'icon': 'fa-male'},
        {'name': "Women's Shoes", 'icon': 'fa-female'},
        {'name': 'Kids Shoes', 'icon': 'fa-child'},
        {'name': 'Luxury', 'icon': 'fa-crown'},
    ]

    for cd in categories_data:
        cat = Category(name=cd['name'], slug=slugify(cd['name']), icon=cd['icon'])
        db.session.add(cat)

    db.session.commit()
    return '12 categories created! <a href="/admin/products/add">Add your first product →</a>'


# ===================== ERROR HANDLERS =====================

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


# ===================== MAIN =====================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'production') == 'development'
    app.run(debug=debug, host='0.0.0.0', port=port)
