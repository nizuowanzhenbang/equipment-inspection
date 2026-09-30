"""Read-only comparison against frozen, dialect-specific database contracts."""
from copy import deepcopy
import json
from pathlib import Path
import warnings

from sqlalchemy import inspect, text
from sqlalchemy.exc import SAWarning


CONTRACTS = Path(__file__).resolve().parents[1] / 'migrations' / 'contracts'
OPTIONAL_COLUMNS = {'work_tickets': 'signatures', 'operation_tickets': 'signatures'}
RECORD_INDEX = 'uq_inspection_record_task_point'


def _validate_serial(connection, table, column):
    quote = connection.dialect.identifier_preparer.quote
    schema = connection.scalar(text('SELECT current_schema()'))
    qualified = quote(schema) + '.' + quote(table)
    owned = connection.execute(text(
        'SELECT c.oid, n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace '
        'WHERE c.oid=pg_get_serial_sequence(:table, :column)::regclass'),
        {'table': qualified, 'column': column}).first()
    referenced = connection.execute(text(
        "SELECT d.refobjid FROM pg_depend d JOIN pg_attrdef a ON a.oid=d.objid "
        "AND d.classid='pg_attrdef'::regclass JOIN pg_attribute v ON v.attrelid=a.adrelid AND v.attnum=a.adnum "
        "JOIN pg_class s ON s.oid=d.refobjid AND s.relkind='S' "
        "WHERE d.refclassid='pg_class'::regclass AND a.adrelid=to_regclass(:table) AND v.attname=:column"),
        {'table': qualified, 'column': column}).scalars().all()
    if (not owned or owned.nspname != schema or owned.relname != f'{table}_{column}_seq'
            or referenced != [owned.oid]):
        raise RuntimeError(f'Unknown database structure: sequence ownership/reference for {table}.{column}')


def describe_schema(connection):
    inspector = inspect(connection)
    result = {}
    for table in sorted(inspector.get_table_names()):
        if table == 'alembic_version':
            continue
        pk = inspector.get_pk_constraint(table)['constrained_columns']
        columns = {}
        for column in inspector.get_columns(table):
            default = column.get('default')
            if default and column['name'] in pk and str(default).startswith('nextval('):
                _validate_serial(connection, table, column['name'])
                default = '<serial>'
            columns[column['name']] = {
                'type': str(column['type']), 'enum': getattr(column['type'], 'enums', None),
                'nullable': column['nullable'], 'default': default,
            }
        foreign_keys = [
            {'columns': f['constrained_columns'], 'table': f['referred_table'],
             'target': f['referred_columns'], 'schema': f.get('referred_schema'), 'options': f.get('options', {})}
            for f in inspector.get_foreign_keys(table)
        ]
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='Skipped unsupported reflection of expression-based index.*', category=SAWarning)
            reflected = inspector.get_indexes(table)
        if connection.dialect.name == 'sqlite':
            quote = connection.dialect.identifier_preparer.quote
            listed = connection.exec_driver_sql(f'PRAGMA index_list({quote(table)})').all()
            if {i[1] for i in listed if i[3] == 'c'} != {i['name'] for i in reflected}:
                raise RuntimeError(f'Unknown database structure: unreflected index on {table}')
            for index in listed:
                keys = connection.exec_driver_sql(f'PRAGMA index_xinfo({quote(index[1])})').all()
                if any(k[1] < 0 or k[3] != 0 or k[4] != 'BINARY' for k in keys if k[5]):
                    raise RuntimeError(f'Unknown database structure: index sorting/collation on {table}')
        indexes = {
            i['name']: {'columns': i['column_names'], 'unique': bool(i['unique']),
                        'expressions': i.get('expressions'),
                        'where': str(i.get('dialect_options', {}).get(f'{connection.dialect.name}_where', ''))}
            for i in reflected
        }
        result[table] = {
            'columns': columns, 'pk': pk,
            'foreign_keys': sorted(foreign_keys, key=lambda item: json.dumps(item, sort_keys=True)),
            'indexes': indexes,
            'unique': sorted([u['column_names'] for u in inspector.get_unique_constraints(table)]),
            'checks': sorted([c['sqltext'] for c in inspector.get_check_constraints(table)]),
        }
    if inspector.get_view_names():
        raise RuntimeError('Unknown database structure: views are not part of the baseline')
    if connection.dialect.name == 'postgresql':
        if inspector.get_materialized_view_names():
            raise RuntimeError('Unknown database structure: materialized views')
        triggers = connection.scalar(text("SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                                          "JOIN pg_namespace n ON n.oid=c.relnamespace "
                                          "WHERE NOT t.tgisinternal AND n.nspname=current_schema()"))
    else:
        triggers = connection.scalar(text("SELECT count(*) FROM sqlite_master WHERE type='trigger'"))
    if triggers:
        raise RuntimeError('Unknown database structure: custom triggers')
    return result


def validate_structure(connection, *, allow_legacy=False):
    dialect = connection.dialect.name
    if dialect not in ('sqlite', 'postgresql'):
        raise RuntimeError('Supported databases are SQLite and PostgreSQL')
    expected = json.loads((CONTRACTS / f'{dialect}.json').read_text(encoding='utf-8'))
    actual = describe_schema(connection)
    if allow_legacy and not actual:
        return 'empty'
    if allow_legacy and set(actual) == {'users', 'audit_logs'}:
        expected = {name: expected[name] for name in actual}
        kind = 'bootstrap'
    else:
        kind = 'legacy' if allow_legacy else 'current'
    comparable = deepcopy(expected)
    if allow_legacy and kind != 'bootstrap':
        for table, column in OPTIONAL_COLUMNS.items():
            if table in actual and column not in actual[table]['columns']:
                comparable[table]['columns'].pop(column)
        if 'inspection_records' in actual and RECORD_INDEX not in actual['inspection_records']['indexes']:
            comparable['inspection_records']['indexes'].pop(RECORD_INDEX)
    if actual != comparable:
        differences = sorted(name for name in set(actual) | set(comparable)
                             if actual.get(name) != comparable.get(name))
        raise RuntimeError('Unknown database structure in tables: ' + ', '.join(differences))
    return kind
