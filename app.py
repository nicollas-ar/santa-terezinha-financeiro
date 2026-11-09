import os, secrets, csv, io
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
from functools import wraps
import click
from flask import Flask, render_template, request, redirect, url_for, flash, abort, session, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
url = os.getenv('DATABASE_URL', 'sqlite:///local.db')
if url.startswith('postgres://'): url = url.replace('postgres://', 'postgresql+psycopg://', 1)
elif url.startswith('postgresql://'): url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
app.config.update(SQLALCHEMY_DATABASE_URI=url, SQLALCHEMY_TRACK_MODIFICATIONS=False, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '0') == '1', PERMANENT_SESSION_LIFETIME=3600, MAX_CONTENT_LENGTH=1024*1024)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    @property
    def is_active(self): return self.active

class Unit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    kind = db.Column(db.String(25), nullable=False)  # comunidade/projeto/campanha/centro_custo
    active = db.Column(db.Boolean, nullable=False, default=True)

class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(10), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(15), nullable=False, default='pendente')
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship('User', foreign_keys=[created_by])
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'))
    unit = db.relationship('Unit')
    due_date = db.Column(db.Date)
    paid_date = db.Column(db.Date)
    reference = db.Column(db.String(100))

class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    entity = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    details = db.Column(db.String(500), nullable=False, default='')
    user = db.relationship('User')

@login_manager.user_loader
def load_user(uid):
    try: return db.session.get(User, int(uid))
    except (ValueError, TypeError): return None

@app.before_request
def check_csrf():
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        token = request.form.get('csrf_token', '')
        if not token or not secrets.compare_digest(token, session.get('csrf_token', '')): abort(400, 'Token CSRF inválido')

@app.context_processor
def common():
    if 'csrf_token' not in session: session['csrf_token'] = secrets.token_urlsafe(32)
    return {'csrf_token': session['csrf_token']}

def priest_only(fn):
    @wraps(fn)
    @login_required
    def inner(*args, **kwargs):
        if current_user.role != 'padre': abort(403)
        return fn(*args, **kwargs)
    return inner

def audit(action, entity, entity_id, details=''):
    db.session.add(Audit(user_id=current_user.id, action=action, entity=entity, entity_id=entity_id, details=details[:500]))

def parse_money(value):
    try: n = Decimal(value.strip().replace(',', '.'))
    except (InvalidOperation, AttributeError): return None
    if not n.is_finite() or n <= 0 or n > Decimal('9999999999.99') or n.as_tuple().exponent < -2: return None
    return n

def parse_date(value):
    if not value: return None
    try: return date.fromisoformat(value)
    except ValueError: raise ValueError('Data inválida')

@app.route('/login', methods=['GET','POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username','').strip(), active=True).first()
        if user and check_password_hash(user.password_hash, request.form.get('password','')):
            session.clear()
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Credenciais inválidas.', 'error')
    return render_template('login.html')

@app.post('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('login'))

@app.get('/')
@login_required
def dashboard():
    q = Entry.query
    if current_user.role != 'padre': q = q.filter_by(created_by=current_user.id)
    else:
        unit_id = request.args.get('unit_id', type=int)
        if unit_id: q = q.filter_by(unit_id=unit_id)
    entries = q.order_by(Entry.created_at.desc(), Entry.id.desc()).limit(150).all()
    totals = {}
    if current_user.role == 'padre':
        tq = db.session.query(Entry.kind, func.sum(Entry.amount)).filter(Entry.status == 'aprovado')
        if request.args.get('unit_id', type=int): tq = tq.filter(Entry.unit_id == request.args.get('unit_id', type=int))
        totals = dict(tq.group_by(Entry.kind).all())
    return render_template('dashboard.html', entries=entries, incoming=totals.get('receita', Decimal('0')), outgoing=totals.get('despesa', Decimal('0')), units=Unit.query.filter_by(active=True).order_by(Unit.name).all(), selected_unit=request.args.get('unit_id', type=int))

@app.post('/entries')
@login_required
def add_entry():
    kind = request.form.get('kind')
    category = request.form.get('category','').strip()[:80]
    description = request.form.get('description','').strip()[:255]
    amount = parse_money(request.form.get('amount'))
    unit_id = request.form.get('unit_id', type=int)
    unit = db.session.get(Unit, unit_id) if unit_id else None
    if kind not in ('receita','despesa') or not category or not description or amount is None or (unit_id and (not unit or not unit.active)):
        flash('Confira os campos do lançamento.', 'error'); return redirect(url_for('dashboard'))
    try: due_date = parse_date(request.form.get('due_date'))
    except ValueError:
        flash('Data inválida.', 'error'); return redirect(url_for('dashboard'))
    entry = Entry(kind=kind, category=category, description=description, amount=amount, unit_id=unit_id, due_date=due_date, reference=request.form.get('reference','').strip()[:100], created_by=current_user.id)
    db.session.add(entry)
    db.session.flush()
    audit('criar', 'lancamento', entry.id, f'{kind} {amount} {category}')
    db.session.commit()
    flash('Lançamento enviado para aprovação.', 'success')
    return redirect(url_for('dashboard'))

@app.post('/entries/<int:entry_id>/<action>')
@priest_only
def review_entry(entry_id, action):
    if action not in ('aprovar','rejeitar'): abort(404)
    entry = db.get_or_404(Entry, entry_id)
    if entry.status != 'pendente': abort(409, 'Lançamento já analisado')
    entry.status = 'aprovado' if action == 'aprovar' else 'rejeitado'
    entry.reviewed_by = current_user.id
    entry.reviewed_at = datetime.now(timezone.utc)
    audit(action, 'lancamento', entry.id, f'R$ {entry.amount}')
    db.session.commit()
    flash('Lançamento analisado.', 'success')
    return redirect(url_for('dashboard'))

@app.post('/entries/<int:entry_id>/paid')
@priest_only
def mark_paid(entry_id):
    entry = db.get_or_404(Entry, entry_id)
    if entry.kind != 'despesa' or entry.status != 'aprovado' or entry.paid_date: abort(409)
    entry.paid_date = date.today()
    audit('quitar', 'lancamento', entry.id, f'Pagamento em {entry.paid_date}')
    db.session.commit()
    flash('Despesa marcada como paga. Esta marcação não altera o saldo registrado.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/units', methods=['GET','POST'])
@priest_only
def units():
    if request.method == 'POST':
        name = request.form.get('name','').strip()[:100]
        kind = request.form.get('kind')
        if not name or kind not in ('comunidade','projeto','campanha','centro_custo') or Unit.query.filter_by(name=name).first():
            flash('Nome inválido ou já existente.', 'error')
        else:
            unit = Unit(name=name, kind=kind)
            db.session.add(unit); db.session.flush(); audit('criar', 'unidade', unit.id, f'{kind}: {name}'); db.session.commit()
            flash('Unidade cadastrada.', 'success')
        return redirect(url_for('units'))
    return render_template('units.html', units=Unit.query.order_by(Unit.kind, Unit.name).all())

@app.post('/units/<int:unit_id>/toggle')
@priest_only
def toggle_unit(unit_id):
    unit = db.get_or_404(Unit, unit_id)
    unit.active = not unit.active
    audit('ativar' if unit.active else 'desativar', 'unidade', unit.id, unit.name)
    db.session.commit()
    return redirect(url_for('units'))

@app.get('/analytics')
@priest_only
def analytics():
    # Aggregate approved records only; use server-side access control.
    from collections import defaultdict
    from calendar import month_abbr
    today = date.today()
    try:
        year = int(request.args.get('year', today.year))
    except ValueError:
        abort(400)
    if year < 2000 or year > 2100: abort(400)
    unit_id = request.args.get('unit_id', type=int)
    if unit_id and not db.session.get(Unit, unit_id): abort(400)
    q = Entry.query.filter(Entry.status == 'aprovado')
    if unit_id: q = q.filter(Entry.unit_id == unit_id)
    # Include prior year for year-over-year comparisons.
    start = datetime(year-1, 1, 1, tzinfo=timezone.utc)
    end = datetime(year+1, 1, 1, tzinfo=timezone.utc)
    rows = q.filter(Entry.created_at >= start, Entry.created_at < end).all()
    months = defaultdict(lambda: {'receita': Decimal('0'), 'despesa': Decimal('0')})
    categories = defaultdict(lambda: Decimal('0'))
    units_data = defaultdict(lambda: {'receita': Decimal('0'), 'despesa': Decimal('0')})
    pending_bills = Decimal('0')
    overdue_bills = Decimal('0')
    upcoming_bills = Decimal('0')
    for e in rows:
        dt = e.created_at.date()
        months[(dt.year, dt.month)][e.kind] += e.amount
        if dt.year == year:
            categories[(e.kind, e.category)] += e.amount
            units_data[e.unit.name if e.unit else 'Sem unidade'][e.kind] += e.amount
            if e.kind == 'despesa' and not e.paid_date:
                pending_bills += e.amount
                if e.due_date and e.due_date < today: overdue_bills += e.amount
                elif e.due_date and e.due_date <= today.replace(day=28) + __import__('datetime').timedelta(days=35): upcoming_bills += e.amount
    labels = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
    def series(y, kind): return [float(months[(y,m)][kind]) for m in range(1,13)]
    revenues, expenses = series(year, 'receita'), series(year, 'despesa')
    previous_revenues, previous_expenses = series(year-1, 'receita'), series(year-1, 'despesa')
    total_revenue = sum(revenues)
    total_expense = sum(expenses)
    def percent(current, previous): return round((current-previous)/previous*100, 1) if previous else None
    category_income = sorted([(k[1], float(v)) for k,v in categories.items() if k[0]=='receita'], key=lambda x:-x[1])[:12]
    category_expense = sorted([(k[1], float(v)) for k,v in categories.items() if k[0]=='despesa'], key=lambda x:-x[1])[:12]
    unit_rows = [{'name': name, 'income':float(t['receita']), 'expense':float(t['despesa']), 'balance':float(t['receita']-t['despesa'])} for name,t in units_data.items()]
    unit_rows.sort(key=lambda x:-x['income'])
    return render_template('analytics.html', year=year, selected_unit=unit_id,
        units=Unit.query.order_by(Unit.name).all(), labels=labels, revenues=revenues,
        expenses=expenses, previous_revenues=previous_revenues, previous_expenses=previous_expenses,
        balances=[a-b for a,b in zip(revenues,expenses)],
        total_revenue=total_revenue, total_expense=total_expense, balance=total_revenue-total_expense,
        income_growth=percent(total_revenue,sum(previous_revenues)),
        expense_growth=percent(total_expense,sum(previous_expenses)),
        category_income=category_income, category_expense=category_expense,
        unit_rows=unit_rows, pending_bills=pending_bills, overdue_bills=overdue_bills,
        upcoming_bills=upcoming_bills)

@app.get('/reports')
@priest_only
def reports():
    month = request.args.get('month', '')
    unit_id = request.args.get('unit_id', type=int)
    q = Entry.query.filter_by(status='aprovado')
    if unit_id: q = q.filter_by(unit_id=unit_id)
    if month:
        try:
            start = date.fromisoformat(month + '-01')
            end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
            q = q.filter(Entry.created_at >= start, Entry.created_at < end)
        except ValueError: abort(400)
    entries = q.order_by(Entry.created_at.desc()).limit(5000).all()
    incoming = sum((e.amount for e in entries if e.kind == 'receita'), Decimal('0'))
    outgoing = sum((e.amount for e in entries if e.kind == 'despesa'), Decimal('0'))
    return render_template('reports.html', entries=entries, incoming=incoming, outgoing=outgoing, month=month, units=Unit.query.order_by(Unit.name).all(), selected_unit=unit_id)

@app.get('/reports.csv')
@priest_only
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['ID','Data','Tipo','Categoria','Descricao','Valor BRL','Status','Unidade','Vencimento','Pagamento','Referencia'])
    for e in Entry.query.order_by(Entry.id).yield_per(500):
        writer.writerow([e.id, e.created_at.date().isoformat(), e.kind, e.category, e.description, str(e.amount).replace('.',','), e.status, e.unit.name if e.unit else '', e.due_date or '', e.paid_date or '', e.reference or ''])
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv; charset=utf-8', headers={'Content-Disposition':'attachment; filename=financas_paroquia.csv', 'Cache-Control':'no-store'})

@app.get('/audit')
@priest_only
def audit_log():
    return render_template('audit.html', logs=Audit.query.order_by(Audit.id.desc()).limit(250).all())

@app.route('/users', methods=['GET','POST'])
@priest_only
def users():
    if request.method == 'POST':
        username = request.form.get('username','').strip()[:80]
        role = request.form.get('role')
        password = request.form.get('password','')
        if not username or role not in ('padre','secretaria') or len(password) < 12 or User.query.filter_by(username=username).first():
            flash('Confira usuário, perfil e senha (mínimo 12 caracteres).', 'error')
        else:
            user = User(username=username, role=role, password_hash=generate_password_hash(password))
            db.session.add(user); db.session.flush(); audit('criar', 'usuario', user.id, role); db.session.commit()
            flash('Usuário criado.', 'success')
        return redirect(url_for('users'))
    return render_template('users.html', users=User.query.order_by(User.username).all())

@app.post('/users/<int:user_id>/toggle')
@priest_only
def toggle_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id: abort(400, 'Não é possível desativar a própria conta')
    user.active = not user.active
    audit('ativar' if user.active else 'desativar', 'usuario', user.id, user.username)
    db.session.commit()
    return redirect(url_for('users'))

@app.cli.command('init-db')
def init_db():
    db.create_all()
    print('Tabelas criadas. Para atualizar banco existente, veja README sobre migrações.')

@app.cli.command('create-user')
def create_user():
    import getpass
    username = input('Usuário: ').strip()
    role = input('Perfil (padre/secretaria): ').strip()
    if role not in ('padre','secretaria') or not username or User.query.filter_by(username=username).first(): raise ValueError('Dados inválidos')
    password = getpass.getpass('Senha (mínimo 12 caracteres): ')
    if len(password) < 12: raise ValueError('Senha muito curta')
    db.session.add(User(username=username, role=role, password_hash=generate_password_hash(password)))
    db.session.commit()
    print('Usuário criado.')

if __name__ == '__main__': app.run(debug=False)


@app.cli.command('seed-parish-units')
def seed_parish_units():
    """Cadastra a paróquia e a capela sem duplicar registros existentes."""
    for name in ('Santa Terezinha do Menino Jesus', 'Capela Santa Luzia'):
        if not Unit.query.filter_by(name=name).first():
            db.session.add(Unit(name=name, kind='comunidade'))
            click.echo(f'Criada unidade: {name}')
        else:
            click.echo(f'Unidade já existente: {name}')
    db.session.commit()