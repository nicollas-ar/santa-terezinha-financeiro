import os, secrets, csv, io
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
import click
from flask import Flask, render_template, request, redirect, url_for, flash, abort, session, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, UniqueConstraint
from sqlalchemy.exc import IntegrityError
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
    payment_method = db.Column(db.String(30))

class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    entity = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    details = db.Column(db.String(500), nullable=False, default='')
    user = db.relationship('User')


class StaffPermission(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    can_entries = db.Column(db.Boolean, nullable=False, default=False)
    can_collections = db.Column(db.Boolean, nullable=False, default=True)
    can_income = db.Column(db.Boolean, nullable=False, default=False)
    can_expenses = db.Column(db.Boolean, nullable=False, default=False)
    can_confirm = db.Column(db.Boolean, nullable=False, default=False)
    can_reports = db.Column(db.Boolean, nullable=False, default=False)

class MassSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(110), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'), nullable=False)
    unit = db.relationship('Unit')
    frequency = db.Column(db.String(12), nullable=False)
    weekday = db.Column(db.Integer)
    month_day = db.Column(db.Integer)
    time = db.Column(db.String(5), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)

class MassCollection(db.Model):
    __table_args__ = (UniqueConstraint('schedule_id', 'celebration_date', name='uq_mass_collection_occurrence'),)
    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('mass_schedule.id'), nullable=False)
    schedule = db.relationship('MassSchedule')
    celebration_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recorder = db.relationship('User', foreign_keys=[created_by])
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(12), nullable=False, default='pendente')
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), unique=True)
    entry = db.relationship('Entry')

class ManualCollection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(110), nullable=False)
    celebration_date = db.Column(db.Date, nullable=False)
    celebration_time = db.Column(db.String(5), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'))
    unit = db.relationship('Unit')
    amount = db.Column(db.Numeric(12,2), nullable=False)
    status = db.Column(db.String(12), nullable=False, default='pendente')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recorder = db.relationship('User', foreign_keys=[created_by])
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), unique=True)

def staff_capability(capability):
    if not current_user.is_authenticated or not current_user.active:
        return False
    if current_user.role == 'padre':
        return True
    if current_user.role != 'secretaria':
        return False
    permission = db.session.get(StaffPermission, current_user.id)
    if permission is None:
        return capability == 'entries'  # Compatibilidade com contas antigas.
    if capability == 'entries':
        return bool(permission.can_entries or permission.can_income or permission.can_expenses or permission.can_confirm)
    return bool(getattr(permission, 'can_' + capability, False))

def require_staff(capability):
    if not staff_capability(capability):
        abort(403)

def landing_page():
    return 'dashboard' if staff_capability('entries') else 'collections'

def mass_dates(schedule, today=None):
    today = today or date.today()
    result = []
    for offset in range(-7, 22):
        day = today + timedelta(days=offset)
        if day < schedule.start_date:
            continue
        if schedule.frequency == 'semanal' and day.weekday() == schedule.weekday:
            result.append(day)
        elif schedule.frequency == 'mensal' and day.day == schedule.month_day:
            result.append(day)
    return result

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
    return {'csrf_token': session['csrf_token'], 'staff_capability': staff_capability}

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
    if current_user.is_authenticated: return redirect(url_for(landing_page()))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username','').strip(), active=True).first()
        if user and check_password_hash(user.password_hash, request.form.get('password','')):
            session.clear()
            login_user(user)
            return redirect(url_for(landing_page()))
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
    require_staff('entries')
    q = Entry.query
    if current_user.role != 'padre' and not staff_capability('confirm'): q = q.filter_by(created_by=current_user.id)
    else:
        unit_id = request.args.get('unit_id', type=int)
        if unit_id: q = q.filter_by(unit_id=unit_id)
    entries = q.order_by(Entry.created_at.desc(), Entry.id.desc()).limit(150).all()
    totals = {}
    if current_user.role == 'padre':
        tq = db.session.query(Entry.kind, func.sum(Entry.amount)).filter(Entry.status == 'aprovado')
        if request.args.get('unit_id', type=int): tq = tq.filter(Entry.unit_id == request.args.get('unit_id', type=int))
        totals = dict(tq.group_by(Entry.kind).all())
    # Um só financeiro: Matriz e Capela são origens dos lançamentos, não caixas independentes.
    # O consolidado usa cada lançamento aprovado uma única vez.
    location_summary = []
    if current_user.role == 'padre':
        grouped = db.session.query(Entry.unit_id, Entry.kind, func.sum(Entry.amount)).filter(
            Entry.status == 'aprovado'
        ).group_by(Entry.unit_id, Entry.kind).all()
        areas = [
            ('Matriz Santa Terezinha do Menino Jesus', {'Matriz Santa Terezinha do Menino Jesus', 'Santa Terezinha do Menino Jesus'}),
            ('Capela Santa Luzia', {'Capela Santa Luzia'}),
        ]
        units_by_id = {u.id: u.name for u in Unit.query.all()}
        amounts = {name: {'receita': Decimal('0'), 'despesa': Decimal('0')} for name, _ in areas}
        amounts['Geral / outros projetos'] = {'receita': Decimal('0'), 'despesa': Decimal('0')}
        for unit_key, kind, value in grouped:
            if kind not in ('receita', 'despesa'):
                continue
            origin = units_by_id.get(unit_key)
            area = next((name for name, aliases in areas if origin in aliases), 'Geral / outros projetos')
            amounts[area][kind] += value or Decimal('0')
        for name, values in amounts.items():
            location_summary.append({
                'name': name,
                'income': values['receita'],
                'expense': values['despesa'],
                'balance': values['receita'] - values['despesa'],
            })
    pending_manual = ManualCollection.query.filter_by(status='pendente').order_by(ManualCollection.id.desc()).limit(100).all() if staff_capability('confirm') else []
    return render_template('dashboard.html', pending_manual=pending_manual, entries=entries, incoming=totals.get('receita', Decimal('0')), outgoing=totals.get('despesa', Decimal('0')), units=Unit.query.filter_by(active=True).order_by(Unit.name).all(), selected_unit=request.args.get('unit_id', type=int), location_summary=location_summary)

@app.post('/entries')
@login_required
def add_entry():
    kind = request.form.get('kind')
    if not staff_capability('entries') or (current_user.role != 'padre' and not (staff_capability('income' if kind == 'receita' else 'expenses') or (db.session.get(StaffPermission, current_user.id) is None and kind in ('receita','despesa')))):
        abort(403)
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
    method = request.form.get('payment_method', '')
    if method not in ('pix','dinheiro','cartao','transferencia','outros'):
        flash('Selecione a forma de pagamento ou recebimento.', 'error'); return redirect(url_for('dashboard'))
    entry = Entry(kind=kind, category=category, description=description, amount=amount, unit_id=unit_id, due_date=due_date, reference=request.form.get('reference','').strip()[:100], payment_method=method, created_by=current_user.id)
    db.session.add(entry)
    db.session.flush()
    audit('criar', 'lancamento', entry.id, f'{kind} {amount} {category}')
    db.session.commit()
    flash('Lançamento enviado para aprovação.', 'success')
    return redirect(url_for('dashboard'))

@app.post('/entries/<int:entry_id>/<action>')
@login_required
def review_entry(entry_id, action):
    require_staff('confirm')
    if action not in ('aprovar','rejeitar'): abort(404)
    entry = db.get_or_404(Entry, entry_id)
    if entry.status != 'pendente': abort(409, 'Lançamento já analisado')
    if entry.created_by == current_user.id: abort(403, 'Não é permitido confirmar o próprio lançamento.')
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

@app.route('/users', methods=['GET', 'POST'])
@priest_only
def users():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()[:80]
        role = request.form.get('role')
        password = request.form.get('password', '')
        mode = request.form.get('access_mode', 'collections')
        if (not username or role not in ('padre', 'secretaria') or len(password) < 12
                or User.query.filter_by(username=username).first()
                or (role == 'secretaria' and mode not in ('collections', 'entries', 'both'))):
            flash('Confira usuário, perfil e senha (mínimo 12 caracteres).', 'error')
        else:
            user = User(username=username, role=role, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.flush()
            if role == 'secretaria':
                db.session.add(StaffPermission(user_id=user.id,
                    can_entries=mode in ('entries', 'both'),
                    can_collections=request.form.get('can_collections') == 'on',
                    can_income=request.form.get('can_income') == 'on',
                    can_expenses=request.form.get('can_expenses') == 'on',
                    can_confirm=request.form.get('can_confirm') == 'on',
                    can_reports=request.form.get('can_reports') == 'on'))
            audit('criar', 'usuario', user.id, role)
            db.session.commit()
            flash('Usuário criado com suas permissões.', 'success')
        return redirect(url_for('users'))
    people = User.query.order_by(User.username).all()
    permissions = {p.user_id: p for p in StaffPermission.query.all()}
    return render_template('users.html', users=people, permissions=permissions)

@app.post('/users/<int:user_id>/permissions')
@priest_only
def change_user_permissions(user_id):
    user = db.get_or_404(User, user_id)
    if user.role != 'secretaria':
        abort(400, 'A conta do padre sempre mantém o nível administrativo.')
    # O padre define cada permissão por usuário.
    p = db.session.get(StaffPermission, user.id)
    if p is None:
        p = StaffPermission(user_id=user.id)
        db.session.add(p)
    p.can_entries = any(request.form.get(x) == 'on' for x in ('can_income','can_expenses','can_confirm'))
    p.can_collections = request.form.get('can_collections') == 'on'
    p.can_income = request.form.get('can_income') == 'on'
    p.can_expenses = request.form.get('can_expenses') == 'on'
    p.can_confirm = request.form.get('can_confirm') == 'on'
    p.can_reports = request.form.get('can_reports') == 'on'
    audit('permissoes', 'usuario', user.id, 'Permissões individuais atualizadas')
    db.session.commit()
    flash('Permissões atualizadas.', 'success')
    return redirect(url_for('users'))

@app.post('/users/<int:user_id>/toggle')
@priest_only
def toggle_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id: abort(400, 'Não é possível desativar a própria conta')
    user.active = not user.active
    audit('ativar' if user.active else 'desativar', 'usuario', user.id, user.username)
    db.session.commit()
    return redirect(url_for('users'))


@app.get('/missas')
@priest_only
def masses():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()[:110]
        frequency = request.form.get('frequency')
        unit_id = request.form.get('unit_id', type=int)
        unit = db.session.get(Unit, unit_id) if unit_id else None
        time = request.form.get('time', '')
        try: start = date.fromisoformat(request.form.get('start_date', ''))
        except ValueError: start = None
        valid_time = len(time) == 5 and time[2] == ':' and time[:2].isdigit() and time[3:].isdigit() and int(time[:2]) < 24 and int(time[3:]) < 60
        weekday = request.form.get('weekday', type=int)
        month_day = request.form.get('month_day', type=int)
        valid_rule = (frequency == 'semanal' and weekday is not None and 0 <= weekday <= 6) or (frequency == 'mensal' and month_day is not None and 1 <= month_day <= 31)
        if not title or not unit or not unit.active or unit.kind != 'comunidade' or not valid_time or not start or not valid_rule:
            flash('Revise os campos e escolha uma comunidade ativa.', 'error')
        else:
            schedule = MassSchedule(title=title, frequency=frequency, unit_id=unit.id,
                time=time, start_date=start,
                weekday=weekday if frequency == 'semanal' else None,
                month_day=month_day if frequency == 'mensal' else None)
            db.session.add(schedule)
            db.session.flush()
            audit('criar', 'missa', schedule.id, title)
            db.session.commit()
            flash('Missa recorrente cadastrada.', 'success')
        return redirect(url_for('masses'))
    schedules = MassSchedule.query.order_by(MassSchedule.active.desc(), MassSchedule.title).all()
    church_units = Unit.query.filter_by(active=True, kind='comunidade').order_by(Unit.name).all()
    pending = MassCollection.query.filter_by(status='pendente').order_by(MassCollection.created_at.desc()).all()
    recent = MassCollection.query.order_by(MassCollection.created_at.desc()).limit(30).all()
    return render_template('masses.html', schedules=schedules, units=church_units,
                           pending=pending, recent=recent, today=date.today())

@app.post('/missas/<int:schedule_id>/toggle')
@priest_only
def toggle_mass(schedule_id):
    schedule = db.get_or_404(MassSchedule, schedule_id)
    schedule.active = not schedule.active
    audit('ativar' if schedule.active else 'desativar', 'missa', schedule.id, schedule.title)
    db.session.commit()
    return redirect(url_for('masses'))

@app.get('/coletas')
@login_required
def collections():
    require_staff('collections')
    schedules = MassSchedule.query.filter_by(active=True).order_by(MassSchedule.time).all()
    today = date.today()
    existing = {(r.schedule_id, r.celebration_date) for r in MassCollection.query.filter(
        MassCollection.celebration_date >= today - timedelta(days=7),
        MassCollection.celebration_date <= today + timedelta(days=21)).all()}
    upcoming = []
    for schedule in schedules:
        for day in mass_dates(schedule, today):
            if day <= today and (schedule.id, day) not in existing:
                upcoming.append({'schedule': schedule, 'date': day})
    upcoming.sort(key=lambda item: (item['date'], item['schedule'].time, item['schedule'].title))
    records = MassCollection.query.filter_by(created_by=current_user.id).order_by(
        MassCollection.created_at.desc()).limit(12).all()
    manual_records = ManualCollection.query.filter_by(created_by=current_user.id).order_by(ManualCollection.id.desc()).limit(12).all()
    units = Unit.query.filter_by(active=True, kind='comunidade').order_by(Unit.name).all()
    return render_template('collections.html', upcoming=upcoming, records=records, manual_records=manual_records, units=units, today=today)

@app.post('/coletas')
@login_required
def submit_collection():
    require_staff('collections')
    schedule = db.get_or_404(MassSchedule, request.form.get('schedule_id', type=int))
    try: day = date.fromisoformat(request.form.get('celebration_date', ''))
    except ValueError: abort(400)
    if not schedule.active or day > date.today() or day not in mass_dates(schedule):
        abort(400, 'Missa fora do período permitido.')
    amount = parse_money(request.form.get('amount', ''))
    if amount is None:
        flash('Digite o valor arrecadado, maior que zero.', 'error')
        return redirect(url_for('collections'))
    if MassCollection.query.filter_by(schedule_id=schedule.id, celebration_date=day).first():
        flash('A coleta desta missa já foi informada.', 'error')
        return redirect(url_for('collections'))
    collection = MassCollection(schedule_id=schedule.id, celebration_date=day,
        amount=amount, created_by=current_user.id)
    db.session.add(collection)
    try:
        db.session.flush()
        audit('registrar', 'coleta', collection.id, f'R$ {amount}')
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('Esta missa já tem uma coleta cadastrada.', 'error')
        return redirect(url_for('collections'))
    flash('Coleta enviada! O padre vai conferir e aprovar.', 'success')
    return redirect(url_for('collections'))

@app.post('/coletas/<int:collection_id>/<action>')
@login_required
def review_collection(collection_id, action):
    require_staff('confirm')
    if action not in ('aprovar', 'rejeitar'): abort(404)
    collection = db.session.query(MassCollection).filter_by(id=collection_id).with_for_update().first()
    if collection is None: abort(404)
    if collection.status != 'pendente': abort(409, 'Coleta já analisada.')
    if collection.created_by == current_user.id: abort(403, 'Não é permitido confirmar a própria coleta.')
    if action == 'aprovar':
        entry = Entry(kind='receita', category='Coleta',
            description=f'Coleta da missa {collection.schedule.title} em {collection.celebration_date.strftime("%d/%m/%Y")}',
            amount=collection.amount, status='aprovado',
            created_by=collection.created_by, reviewed_by=current_user.id,
            reviewed_at=datetime.now(timezone.utc), unit_id=collection.schedule.unit_id,
            reference=f'coleta-missa-{collection.id}')
        db.session.add(entry)
        db.session.flush()
        collection.entry_id = entry.id
        collection.status = 'aprovado'
    else:
        collection.status = 'rejeitado'
    collection.reviewed_by = current_user.id
    collection.reviewed_at = datetime.now(timezone.utc)
    audit(action, 'coleta', collection.id, f'R$ {collection.amount}')
    db.session.commit()
    flash('Coleta analisada com sucesso.', 'success')
    return redirect(url_for('dashboard'))

@app.post('/coletas/manuais')
@login_required
def submit_manual_collection():
    require_staff('collections')
    title = request.form.get('title','').strip()[:110]
    time = request.form.get('time','')
    amount = parse_money(request.form.get('amount',''))
    try: day = parse_date(request.form.get('celebration_date'))
    except ValueError: day = None
    unit_id = request.form.get('unit_id',type=int)
    unit = db.session.get(Unit,unit_id) if unit_id else None
    valid_time = len(time)==5 and time[2]==':' and time[:2].isdigit() and time[3:].isdigit() and int(time[:2])<24 and int(time[3:])<60
    if not title or not valid_time or not day or day > date.today() or amount is None or (unit_id and (not unit or not unit.active)):
        flash('Revise os dados da celebração.','error'); return redirect(url_for('collections'))
    duplicate = ManualCollection.query.filter_by(title=title, celebration_date=day, celebration_time=time, unit_id=unit_id).filter(ManualCollection.status != 'rejeitado').first()
    if duplicate:
        flash('Já existe uma arrecadação para esta celebração, data, horário e local. Confira antes de cadastrar novamente.', 'error')
        return redirect(url_for('collections'))
    c = ManualCollection(title=title, celebration_date=day, celebration_time=time, amount=amount, unit_id=unit_id, created_by=current_user.id)
    db.session.add(c); db.session.flush(); audit('registrar','coleta_manual',c.id,f'R$ {amount}'); db.session.commit()
    flash('Arrecadação registrada e aguardando segunda assinatura.','success')
    return redirect(url_for('collections'))

@app.post('/coletas/manuais/<int:collection_id>/<action>')
@login_required
def review_manual_collection(collection_id,action):
    require_staff('confirm')
    if action not in ('aprovar','rejeitar'): abort(404)
    c = ManualCollection.query.filter_by(id=collection_id).with_for_update().first()
    if c is None: abort(404)
    if c.status != 'pendente': abort(409)
    if c.created_by == current_user.id: abort(403, 'Não é permitido confirmar o próprio lançamento.')
    c.status = 'aprovado' if action == 'aprovar' else 'rejeitado'
    c.reviewed_by = current_user.id
    c.reviewed_at = datetime.now(timezone.utc)
    if action == 'aprovar':
        entry = Entry(kind='receita',category='Coleta',description=f'{c.title} em {c.celebration_date:%d/%m/%Y} às {c.celebration_time}',amount=c.amount,status='aprovado',created_by=c.created_by,reviewed_by=current_user.id,reviewed_at=c.reviewed_at,unit_id=c.unit_id,reference=f'coleta-manual-{c.id}')
        db.session.add(entry); db.session.flush(); c.entry_id = entry.id
    audit(action,'coleta_manual',c.id,f'R$ {c.amount}'); db.session.commit()
    flash('Arrecadação analisada.','success')
    return redirect(url_for('dashboard'))

@app.cli.command('init-db')
def init_db():
    db.create_all()
    print('Tabelas criadas. Para atualizar banco existente, veja README sobre migrações.')

@app.cli.command('upgrade-collections')
def upgrade_collections():
    """Cria somente as tabelas adicionais sem alterar lançamentos existentes."""
    db.metadata.create_all(bind=db.engine, tables=[StaffPermission.__table__, MassSchedule.__table__, MassCollection.__table__, ManualCollection.__table__])
    print('Tabelas de permissões, missas e coletas criadas sem apagar dados.')

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
    """Configura Matriz e Capela no caixa paroquial único, preservando lançamentos."""
    matrix_name = 'Matriz Santa Terezinha do Menino Jesus'
    old_name = 'Santa Terezinha do Menino Jesus'
    chapel_name = 'Capela Santa Luzia'
    matrix = Unit.query.filter_by(name=matrix_name).first()
    legacy = Unit.query.filter_by(name=old_name).first()
    if not matrix and legacy:
        legacy.name = matrix_name  # Mantém ID e todos os lançamentos existentes.
        legacy.kind = 'comunidade'
        legacy.active = True
        click.echo('Matriz renomeada sem alterar seus lançamentos.')
    elif not matrix:
        db.session.add(Unit(name=matrix_name, kind='comunidade'))
        click.echo('Matriz cadastrada.')
    else:
        matrix.active = True
        click.echo('Matriz já cadastrada.')
    chapel = Unit.query.filter_by(name=chapel_name).first()
    if not chapel:
        db.session.add(Unit(name=chapel_name, kind='comunidade'))
        click.echo('Capela Santa Luzia cadastrada.')
    else:
        chapel.active = True
        click.echo('Capela Santa Luzia já cadastrada.')
    if matrix and legacy:
        click.echo('Atenção: existem Matriz e unidade antiga; revise os vínculos antigos manualmente.')
    db.session.commit()
    click.echo('Unidades prontas. O financeiro consolidado continua único.')

@app.cli.command('upgrade-financeiro')
def upgrade_financeiro():
    """Migração aditiva: não exclui dados antigos."""
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    with db.engine.begin() as conn:
        if 'staff_permission' in inspector.get_table_names():
            existing = {c['name'] for c in inspector.get_columns('staff_permission')}
            for col in ('can_income','can_expenses','can_confirm','can_reports'):
                if col not in existing:
                    conn.execute(text(f'ALTER TABLE staff_permission ADD COLUMN {col} BOOLEAN NOT NULL DEFAULT FALSE'))
            conn.execute(text('UPDATE staff_permission SET can_income = TRUE, can_expenses = TRUE WHERE can_entries = TRUE AND can_income = FALSE AND can_expenses = FALSE'))
        if 'entry' in inspector.get_table_names() and 'payment_method' not in {c['name'] for c in inspector.get_columns('entry')}:
            conn.execute(text('ALTER TABLE entry ADD COLUMN payment_method VARCHAR(30)'))
    db.metadata.create_all(bind=db.engine, tables=[StaffPermission.__table__,ManualCollection.__table__])
    click.echo('Migração aditiva concluída; nenhum lançamento removido.')

def migrate_on_startup():
    """Atualiza o esquema antes de aceitar requisições no Render (sem Shell)."""
    from sqlalchemy import inspect, text
    with app.app_context():
        with db.engine.begin() as conn:
            # Serializa inicializações concorrentes de workers Gunicorn no PostgreSQL.
            if conn.dialect.name == 'postgresql':
                conn.execute(text('SELECT pg_advisory_xact_lock(72638421)'))
            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            if 'staff_permission' in tables:
                columns = {c['name'] for c in inspector.get_columns('staff_permission')}
                for name in ('can_income', 'can_expenses', 'can_confirm', 'can_reports'):
                    if name not in columns:
                        conn.execute(text(f'ALTER TABLE staff_permission ADD COLUMN {name} BOOLEAN NOT NULL DEFAULT FALSE'))
                conn.execute(text('UPDATE staff_permission SET can_income = TRUE, can_expenses = TRUE WHERE can_entries = TRUE AND can_income = FALSE AND can_expenses = FALSE'))
            if 'entry' in tables:
                columns = {c['name'] for c in inspector.get_columns('entry')}
                if 'payment_method' not in columns:
                    conn.execute(text('ALTER TABLE entry ADD COLUMN payment_method VARCHAR(30)'))
            StaffPermission.__table__.create(bind=conn, checkfirst=True)
            ManualCollection.__table__.create(bind=conn, checkfirst=True)
    app.logger.info('Migração financeira de inicialização concluída.')

migrate_on_startup()

