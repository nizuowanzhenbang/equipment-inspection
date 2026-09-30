"""Frozen model structure captured at dfb394b; never import live ORM here."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001_frozen_baseline'
down_revision = None
branch_labels = None
depends_on = None


def frozen_enum(*labels, name):
    if op.get_bind().dialect.name == 'postgresql':
        enum = postgresql.ENUM(*labels, name=name, create_type=False)
        enum.create(op.get_bind(), checkfirst=True)
        return enum
    return sa.Enum(*labels, name=name)


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'audit_logs' not in existing:
        op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor', sa.String(length=50), nullable=True, comment='操作人 username'),
        sa.Column('action', sa.String(length=80), nullable=False, comment='动作标识，如 defect.create / wt.issue'),
        sa.Column('target_type', sa.String(length=50), nullable=True, comment='对象类型 Defect/WorkTicket/...'),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('target_no', sa.String(length=50), nullable=True, comment='对象业务编号 (defect_no/ticket_no)'),
        sa.Column('summary', sa.String(length=300), nullable=True, comment='可读摘要'),
        sa.Column('extra', sa.JSON(), nullable=True, comment='附加结构化字段'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
    if 'audit_logs' not in existing:
        op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
        op.create_index(op.f('ix_audit_logs_actor'), 'audit_logs', ['actor'], unique=False)
        op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
        op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)
        op.create_index(op.f('ix_audit_logs_target_id'), 'audit_logs', ['target_id'], unique=False)
        op.create_index(op.f('ix_audit_logs_target_no'), 'audit_logs', ['target_no'], unique=False)
        op.create_index(op.f('ix_audit_logs_target_type'), 'audit_logs', ['target_type'], unique=False)
    if 'equipments' not in existing:
        op.create_table('equipments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False, comment='设备编号 EQ-XX-NNNN'),
        sa.Column('name', sa.String(length=100), nullable=False, comment='设备名称'),
        sa.Column('equipment_system', frozen_enum('BOILER', 'TURBINE', 'GENERATOR', 'AUXILIARY', 'ELECTRICAL', 'CHEMICAL', 'ASH', 'DESULFUR', name='equipmentsystem'), nullable=False, comment='所属系统'),
        sa.Column('criticality', frozen_enum('A', 'B', 'C', name='criticality'), nullable=False, comment='重要性等级'),
        sa.Column('location', sa.String(length=100), nullable=True, comment='安装位置/区域'),
        sa.Column('model', sa.String(length=100), nullable=True, comment='设备型号'),
        sa.Column('manufacturer', sa.String(length=100), nullable=True, comment='生产厂家'),
        sa.Column('install_date', sa.Date(), nullable=True, comment='投运日期'),
        sa.Column('status', frozen_enum('RUNNING', 'STANDBY', 'MAINTENANCE', 'DECOMMISSIONED', name='equipmentstatus'), nullable=False),
        sa.Column('qr_code', sa.String(length=200), nullable=True, comment='二维码内容（设备唯一标识）'),
        sa.Column('health_score', sa.Integer(), nullable=True, comment='健康度评分 0-100'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
    if 'equipments' not in existing:
        op.create_index(op.f('ix_equipments_code'), 'equipments', ['code'], unique=True)
        op.create_index(op.f('ix_equipments_criticality'), 'equipments', ['criticality'], unique=False)
        op.create_index(op.f('ix_equipments_equipment_system'), 'equipments', ['equipment_system'], unique=False)
        op.create_index(op.f('ix_equipments_id'), 'equipments', ['id'], unique=False)
        op.create_index(op.f('ix_equipments_status'), 'equipments', ['status'], unique=False)
    if 'inspection_routes' not in existing:
        op.create_table('inspection_routes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('route_no', sa.String(length=50), nullable=False, comment='路线编号 RT-NNN'),
        sa.Column('name', sa.String(length=100), nullable=False, comment='路线名称（如：1#机组锅炉一班巡检）'),
        sa.Column('equipment_system', sa.String(length=50), nullable=True, comment='主要覆盖系统'),
        sa.Column('frequency', frozen_enum('SHIFT', 'DAILY', 'WEEKLY', 'MONTHLY', name='routefrequency'), nullable=False, comment='计划频率'),
        sa.Column('estimated_duration', sa.Integer(), nullable=True, comment='预计耗时（分钟）'),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
    if 'inspection_routes' not in existing:
        op.create_index(op.f('ix_inspection_routes_id'), 'inspection_routes', ['id'], unique=False)
        op.create_index(op.f('ix_inspection_routes_route_no'), 'inspection_routes', ['route_no'], unique=True)
    if 'operation_templates' not in existing:
        op.create_table('operation_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False, comment='模板名称（业务唯一）'),
        sa.Column('operation_type', frozen_enum('POWER_OFF', 'POWER_ON', 'SWITCHING', 'OTHER', name='operationtickettype'), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('steps', sa.JSON(), nullable=False, comment='模板步骤 [{seq,action,expected}]'),
        sa.Column('use_count', sa.Integer(), nullable=True, comment='被复用次数'),
        sa.Column('created_by', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
        )
    if 'operation_templates' not in existing:
        op.create_index(op.f('ix_operation_templates_id'), 'operation_templates', ['id'], unique=False)
    if 'spare_parts' not in existing:
        op.create_table('spare_parts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False, comment='物料编号 SP-NNNN'),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('spec', sa.String(length=200), nullable=True, comment='规格型号'),
        sa.Column('unit', sa.String(length=20), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=True, comment='分类：轴承/密封件/电子件/油料/工具...'),
        sa.Column('stock_qty', sa.Numeric(precision=10, scale=2), nullable=True, comment='当前库存数量'),
        sa.Column('min_qty', sa.Numeric(precision=10, scale=2), nullable=True, comment='安全库存（低于即预警）'),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=True, comment='单价（元）'),
        sa.Column('location', sa.String(length=100), nullable=True, comment='存放位置（仓位）'),
        sa.Column('supplier', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
    if 'spare_parts' not in existing:
        op.create_index(op.f('ix_spare_parts_code'), 'spare_parts', ['code'], unique=True)
        op.create_index(op.f('ix_spare_parts_id'), 'spare_parts', ['id'], unique=False)
    if 'users' not in existing:
        op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('full_name', sa.String(length=50), nullable=True),
        sa.Column('hashed_password', sa.String(length=200), nullable=False),
        sa.Column('role', frozen_enum('ADMIN', 'INSPECTOR', 'REPAIRMAN', 'SUPERVISOR', 'VIEWER', name='userrole'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
    if 'users' not in existing:
        op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
        op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    if 'defects' not in existing:
        op.create_table('defects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('defect_no', sa.String(length=50), nullable=False, comment='缺陷单号 DF-YYYYMMDD-NNNN'),
        sa.Column('equipment_id', sa.Integer(), nullable=False),
        sa.Column('source', frozen_enum('INSPECTION', 'MANUAL', 'ALARM', name='defectsource'), nullable=False),
        sa.Column('severity', frozen_enum('MINOR', 'MAJOR', 'CRITICAL', name='defectseverity'), nullable=False),
        sa.Column('status', frozen_enum('NEW', 'ASSIGNED', 'IN_REPAIR', 'REPAIRED', 'VERIFIED', 'CLOSED', 'OVERDUE', 'CANCELLED', name='defectstatus'), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False, comment='标题'),
        sa.Column('description', sa.Text(), nullable=True, comment='问题描述'),
        sa.Column('photo_url', sa.String(length=300), nullable=True),
        sa.Column('reported_by', sa.String(length=50), nullable=True, comment='上报人'),
        sa.Column('reported_at', sa.DateTime(), nullable=True),
        sa.Column('assigned_to', sa.String(length=50), nullable=True, comment='指派维修工'),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.Column('assigned_by', sa.String(length=50), nullable=True),
        sa.Column('repair_started_at', sa.DateTime(), nullable=True),
        sa.Column('repair_completed_at', sa.DateTime(), nullable=True),
        sa.Column('repair_notes', sa.Text(), nullable=True, comment='检修记录'),
        sa.Column('repair_cost', sa.Integer(), nullable=True, comment='检修费用（元）'),
        sa.Column('verified_by', sa.String(length=50), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('verify_notes', sa.Text(), nullable=True),
        sa.Column('sla_deadline', sa.DateTime(), nullable=True, comment='SLA 截止时间'),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('safety_sync_status', sa.String(length=20), nullable=True, comment='联动状态 PENDING/SYNCED/FAILED/SKIPPED'),
        sa.Column('safety_hazard_no', sa.String(length=50), nullable=True, comment='对应隐患单号（plant-safety 返回）'),
        sa.Column('safety_sync_at', sa.DateTime(), nullable=True),
        sa.Column('safety_sync_error', sa.String(length=300), nullable=True),
        sa.Column('safety_sync_attempts', sa.Integer(), nullable=False, comment='重试次数'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipments.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if 'defects' not in existing:
        op.create_index(op.f('ix_defects_defect_no'), 'defects', ['defect_no'], unique=True)
        op.create_index(op.f('ix_defects_equipment_id'), 'defects', ['equipment_id'], unique=False)
        op.create_index(op.f('ix_defects_id'), 'defects', ['id'], unique=False)
        op.create_index(op.f('ix_defects_severity'), 'defects', ['severity'], unique=False)
        op.create_index(op.f('ix_defects_status'), 'defects', ['status'], unique=False)
    if 'inspection_points' not in existing:
        op.create_table('inspection_points',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('point_no', sa.String(length=50), nullable=False, comment='测点编号 PT-NNNN'),
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('equipment_id', sa.Integer(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False, comment='路线内顺序'),
        sa.Column('check_items', sa.JSON(), nullable=False, comment='检查项数组：[{name,type:NUM/BOOL/SELECT,unit?,min?,max?,options?}]'),
        sa.Column('standard', sa.Text(), nullable=True, comment='检查标准/合格判据'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipments.id'], ),
        sa.ForeignKeyConstraint(['route_id'], ['inspection_routes.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if 'inspection_points' not in existing:
        op.create_index(op.f('ix_inspection_points_equipment_id'), 'inspection_points', ['equipment_id'], unique=False)
        op.create_index(op.f('ix_inspection_points_id'), 'inspection_points', ['id'], unique=False)
        op.create_index(op.f('ix_inspection_points_point_no'), 'inspection_points', ['point_no'], unique=True)
        op.create_index(op.f('ix_inspection_points_route_id'), 'inspection_points', ['route_id'], unique=False)
    if 'inspection_tasks' not in existing:
        op.create_table('inspection_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_no', sa.String(length=50), nullable=False, comment='任务编号 TK-YYYYMMDD-NNNN'),
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(), nullable=False, comment='计划执行时间'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('assigned_to', sa.String(length=50), nullable=True, comment='指派点检员（username）'),
        sa.Column('executed_by', sa.String(length=50), nullable=True, comment='实际执行人'),
        sa.Column('status', frozen_enum('PENDING', 'IN_PROGRESS', 'COMPLETED', 'MISSED', 'CANCELLED', name='taskstatus'), nullable=False),
        sa.Column('abnormal_count', sa.Integer(), nullable=True, comment='本任务发现的异常测点数'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['route_id'], ['inspection_routes.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if 'inspection_tasks' not in existing:
        op.create_index(op.f('ix_inspection_tasks_id'), 'inspection_tasks', ['id'], unique=False)
        op.create_index(op.f('ix_inspection_tasks_route_id'), 'inspection_tasks', ['route_id'], unique=False)
        op.create_index(op.f('ix_inspection_tasks_scheduled_at'), 'inspection_tasks', ['scheduled_at'], unique=False)
        op.create_index(op.f('ix_inspection_tasks_status'), 'inspection_tasks', ['status'], unique=False)
        op.create_index(op.f('ix_inspection_tasks_task_no'), 'inspection_tasks', ['task_no'], unique=True)
    if 'purchase_requests' not in existing:
        op.create_table('purchase_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pr_no', sa.String(length=50), nullable=False, comment='PR-YYYYMMDD-NNNN'),
        sa.Column('spare_part_id', sa.Integer(), nullable=False),
        sa.Column('qty', sa.Numeric(precision=10, scale=2), nullable=False, comment='申请采购数量'),
        sa.Column('estimated_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='预估金额 = qty × unit_price'),
        sa.Column('urgency', sa.String(length=20), nullable=True, comment='NORMAL / URGENT'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('source', frozen_enum('AUTO_LOW_STOCK', 'MANUAL', name='prsource'), nullable=False),
        sa.Column('status', frozen_enum('DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'SENT', 'RECEIVED', 'CANCELLED', name='prstatus'), nullable=False),
        sa.Column('applicant', sa.String(length=50), nullable=True),
        sa.Column('approver', sa.String(length=50), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('rejected_reason', sa.Text(), nullable=True),
        sa.Column('external_order_no', sa.String(length=100), nullable=True, comment='对端订单号 PO-...'),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=True),
        sa.Column('received_qty', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['spare_part_id'], ['spare_parts.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if 'purchase_requests' not in existing:
        op.create_index(op.f('ix_purchase_requests_external_order_no'), 'purchase_requests', ['external_order_no'], unique=False)
        op.create_index(op.f('ix_purchase_requests_id'), 'purchase_requests', ['id'], unique=False)
        op.create_index(op.f('ix_purchase_requests_pr_no'), 'purchase_requests', ['pr_no'], unique=True)
        op.create_index(op.f('ix_purchase_requests_spare_part_id'), 'purchase_requests', ['spare_part_id'], unique=False)
        op.create_index(op.f('ix_purchase_requests_status'), 'purchase_requests', ['status'], unique=False)
    if 'inspection_records' not in existing:
        op.create_table('inspection_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('point_id', sa.Integer(), nullable=False),
        sa.Column('status', frozen_enum('NORMAL', 'ABNORMAL', 'SEVERE', name='pointstatus'), nullable=False),
        sa.Column('readings', sa.JSON(), nullable=True, comment='检查项读数：{name: value, ...}'),
        sa.Column('finding', sa.Text(), nullable=True, comment='发现的问题描述'),
        sa.Column('photo_url', sa.String(length=300), nullable=True, comment='现场照片 URL'),
        sa.Column('recorded_by', sa.String(length=50), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=True),
        sa.Column('defect_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['defect_id'], ['defects.id'], ),
        sa.ForeignKeyConstraint(['point_id'], ['inspection_points.id'], ),
        sa.ForeignKeyConstraint(['task_id'], ['inspection_tasks.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if 'inspection_records' not in existing:
        op.create_index(op.f('ix_inspection_records_defect_id'), 'inspection_records', ['defect_id'], unique=False)
        op.create_index(op.f('ix_inspection_records_id'), 'inspection_records', ['id'], unique=False)
        op.create_index(op.f('ix_inspection_records_point_id'), 'inspection_records', ['point_id'], unique=False)
        op.create_index(op.f('ix_inspection_records_status'), 'inspection_records', ['status'], unique=False)
        op.create_index(op.f('ix_inspection_records_task_id'), 'inspection_records', ['task_id'], unique=False)
        op.create_index('uq_inspection_record_task_point', 'inspection_records', ['task_id', 'point_id'], unique=True)
    if 'work_tickets' not in existing:
        op.create_table('work_tickets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_no', sa.String(length=50), nullable=False, comment='WT-YYYYMMDD-NNNN'),
        sa.Column('ticket_type', frozen_enum('FIRST', 'SECOND', 'EMERGENCY', name='worktickettype'), nullable=False),
        sa.Column('defect_id', sa.Integer(), nullable=True, comment='关联的缺陷'),
        sa.Column('equipment_id', sa.Integer(), nullable=False),
        sa.Column('work_content', sa.Text(), nullable=False, comment='工作内容/任务说明'),
        sa.Column('safety_measures', sa.JSON(), nullable=True, comment='安全措施清单：[{seq,measure,checked,checked_by}]'),
        sa.Column('risk_notes', sa.Text(), nullable=True, comment='危险点分析'),
        sa.Column('planned_start', sa.DateTime(), nullable=True),
        sa.Column('planned_end', sa.DateTime(), nullable=True),
        sa.Column('actual_start', sa.DateTime(), nullable=True),
        sa.Column('actual_end', sa.DateTime(), nullable=True),
        sa.Column('applicant', sa.String(length=50), nullable=True, comment='申请人/起草人'),
        sa.Column('principal', sa.String(length=50), nullable=True, comment='工作负责人'),
        sa.Column('issuer', sa.String(length=50), nullable=True, comment='签发人（supervisor）'),
        sa.Column('permitter', sa.String(length=50), nullable=True, comment='许可人'),
        sa.Column('team_members', sa.JSON(), nullable=True, comment='工作班成员 username 列表'),
        sa.Column('status', frozen_enum('DRAFT', 'SUBMITTED', 'ISSUED', 'IN_WORK', 'COMPLETED', 'CLOSED', 'CANCELLED', name='workticketstatus'), nullable=False),
        sa.Column('submitted_at', sa.DateTime(), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('permitted_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('approval_notes', sa.Text(), nullable=True, comment='签发备注'),
        sa.Column('closing_notes', sa.Text(), nullable=True, comment='收票备注'),
        sa.Column('signatures', sa.JSON(), nullable=True, comment='签名链：issue/permit/close 等阶段'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['defect_id'], ['defects.id'], ),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipments.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if 'work_tickets' not in existing:
        op.create_index(op.f('ix_work_tickets_defect_id'), 'work_tickets', ['defect_id'], unique=False)
        op.create_index(op.f('ix_work_tickets_equipment_id'), 'work_tickets', ['equipment_id'], unique=False)
        op.create_index(op.f('ix_work_tickets_id'), 'work_tickets', ['id'], unique=False)
        op.create_index(op.f('ix_work_tickets_status'), 'work_tickets', ['status'], unique=False)
        op.create_index(op.f('ix_work_tickets_ticket_no'), 'work_tickets', ['ticket_no'], unique=True)
    if 'operation_tickets' not in existing:
        op.create_table('operation_tickets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_no', sa.String(length=50), nullable=False, comment='OT-YYYYMMDD-NNNN'),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('operation_type', frozen_enum('POWER_OFF', 'POWER_ON', 'SWITCHING', 'OTHER', name='operationtickettype'), nullable=False),
        sa.Column('work_ticket_id', sa.Integer(), nullable=True),
        sa.Column('equipment_id', sa.Integer(), nullable=True),
        sa.Column('operator', sa.String(length=50), nullable=True, comment='操作员'),
        sa.Column('supervisor', sa.String(length=50), nullable=True, comment='监护人'),
        sa.Column('approver', sa.String(length=50), nullable=True, comment='值长（批准人）'),
        sa.Column('steps', sa.JSON(), nullable=False, comment='步骤数组 [{seq,action,expected,executed_at,executed_by,result,notes}]'),
        sa.Column('status', frozen_enum('DRAFT', 'REVIEWED', 'APPROVED', 'EXECUTING', 'COMPLETED', 'CANCELLED', name='operationticketstatus'), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('signatures', sa.JSON(), nullable=True, comment='签名链：review/approve/complete 等阶段'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipments.id'], ),
        sa.ForeignKeyConstraint(['work_ticket_id'], ['work_tickets.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if 'operation_tickets' not in existing:
        op.create_index(op.f('ix_operation_tickets_equipment_id'), 'operation_tickets', ['equipment_id'], unique=False)
        op.create_index(op.f('ix_operation_tickets_id'), 'operation_tickets', ['id'], unique=False)
        op.create_index(op.f('ix_operation_tickets_status'), 'operation_tickets', ['status'], unique=False)
        op.create_index(op.f('ix_operation_tickets_ticket_no'), 'operation_tickets', ['ticket_no'], unique=True)
        op.create_index(op.f('ix_operation_tickets_work_ticket_id'), 'operation_tickets', ['work_ticket_id'], unique=False)
    if 'stock_movements' not in existing:
        op.create_table('stock_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('spare_part_id', sa.Integer(), nullable=False),
        sa.Column('movement_type', frozen_enum('IN', 'OUT', 'ADJUST', name='stockmovementtype'), nullable=False),
        sa.Column('qty', sa.Numeric(precision=10, scale=2), nullable=False, comment='数量（OUT 用正数）'),
        sa.Column('defect_id', sa.Integer(), nullable=True, comment='关联缺陷（领用场景）'),
        sa.Column('work_ticket_id', sa.Integer(), nullable=True),
        sa.Column('operator', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['defect_id'], ['defects.id'], ),
        sa.ForeignKeyConstraint(['spare_part_id'], ['spare_parts.id'], ),
        sa.ForeignKeyConstraint(['work_ticket_id'], ['work_tickets.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if 'stock_movements' not in existing:
        op.create_index(op.f('ix_stock_movements_created_at'), 'stock_movements', ['created_at'], unique=False)
        op.create_index(op.f('ix_stock_movements_defect_id'), 'stock_movements', ['defect_id'], unique=False)
        op.create_index(op.f('ix_stock_movements_id'), 'stock_movements', ['id'], unique=False)
        op.create_index(op.f('ix_stock_movements_movement_type'), 'stock_movements', ['movement_type'], unique=False)
        op.create_index(op.f('ix_stock_movements_spare_part_id'), 'stock_movements', ['spare_part_id'], unique=False)
        op.create_index(op.f('ix_stock_movements_work_ticket_id'), 'stock_movements', ['work_ticket_id'], unique=False)


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore a verified backup into a separate database')
