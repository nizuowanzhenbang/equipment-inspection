"""seed_data：5 用户 + 18 设备覆盖 8 个系统 + 3 条点检路线 + 一周任务（含部分完成与缺陷）

用法：
    python seed_data.py
"""
from datetime import datetime, timedelta, date

from app.database import Base, engine, SessionLocal
from app.api.deps import hash_password
from app.models.user import User, UserRole
from app.models.equipment import Equipment, EquipmentSystem, Criticality, EquipmentStatus
from app.models.route import InspectionRoute, InspectionPoint, RouteFrequency
from app.models.task import InspectionTask, InspectionRecord, TaskStatus, PointStatus
from app.models.defect import Defect, DefectSource, DefectSeverity, DefectStatus
from app.models.ticket import (
    WorkTicket, WorkTicketType, WorkTicketStatus,
    OperationTicket, OperationTicketType, OperationTicketStatus,
)
from app.models.spare_part import SparePart, StockMovement, StockMovementType
from app.utils.helpers import (
    generate_equipment_code, generate_route_no, generate_point_no,
    generate_task_no, generate_defect_no,
    generate_work_ticket_no, generate_operation_ticket_no,
    generate_spare_part_code,
)


EQUIPMENT_SEEDS = [
    # 锅炉系统
    ("BOILER", Criticality.A, "1号锅炉本体", "锅炉房 12m 平台", "上海锅炉厂", "SG-1025/17.5-M888"),
    ("BOILER", Criticality.A, "2号锅炉本体", "锅炉房 12m 平台", "上海锅炉厂", "SG-1025/17.5-M888"),
    ("BOILER", Criticality.B, "1号锅炉给水泵", "锅炉房 0m", "沈阳水泵", "DG500-180"),
    # 汽轮机
    ("TURBINE", Criticality.A, "1号汽轮机", "汽机房 8m", "上海汽轮机厂", "N300-16.7/537/537"),
    ("TURBINE", Criticality.B, "1号汽机润滑油泵", "汽机房 0m", "上海凯泉", "LY-200"),
    # 发电机
    ("GENERATOR", Criticality.A, "1号发电机", "汽机房 8m", "哈尔滨电机", "QFSN-300-2"),
    # 辅机
    ("AUXILIARY", Criticality.B, "1号送风机", "锅炉房西侧", "上海鼓风机", "G4-73-11"),
    ("AUXILIARY", Criticality.B, "1号引风机", "锅炉房东侧", "上海鼓风机", "Y4-73-11"),
    ("AUXILIARY", Criticality.B, "1号一次风机", "锅炉房 4m", "成都电力", "G4-73-08"),
    # 电气
    ("ELECTRICAL", Criticality.A, "主变压器1#", "升压站", "西安西电", "SFP-360000/220"),
    ("ELECTRICAL", Criticality.B, "厂用电6kV配电室", "电气楼 2F", "施耐德", "MVS-30"),
    # 化学
    ("CHEMICAL", Criticality.C, "化学水处理一级反渗透", "化水车间", "上海中沛", "RO-50"),
    ("CHEMICAL", Criticality.C, "凝结水精处理装置", "汽机房 -4m", "上海三泰", "BS-100"),
    # 除灰除渣
    ("ASH", Criticality.C, "1号除尘器", "锅炉房尾部", "福建龙净", "ESP-2x4"),
    ("ASH", Criticality.C, "1号捞渣机", "锅炉底部", "湖北南方", "LZJ-12"),
    # 脱硫脱硝
    ("DESULFUR", Criticality.B, "脱硫吸收塔1#", "脱硫岛", "国电环保", "WFGD-300"),
    ("DESULFUR", Criticality.B, "脱硫浆液循环泵1A", "脱硫岛 0m", "湖南耒阳", "DT-600"),
    ("DESULFUR", Criticality.C, "脱硝SCR反应器1#", "锅炉尾部", "龙源环保", "SCR-300"),
]


def seed_users(db):
    defaults = [
        ("admin",      "admin123",      UserRole.ADMIN,      "李大刚（设备部主任）"),
        ("inspector",  "inspector123",  UserRole.INSPECTOR,  "张师傅（点检员）"),
        ("repairman",  "repairman123",  UserRole.REPAIRMAN,  "王工（维修班）"),
        ("supervisor", "supervisor123", UserRole.SUPERVISOR, "刘工（设备主管）"),
        ("viewer",     "viewer123",     UserRole.VIEWER,     "陈先生（值长）"),
    ]
    for username, pwd, role, full in defaults:
        if db.query(User).filter(User.username == username).first():
            continue
        db.add(User(
            username=username, full_name=full,
            hashed_password=hash_password(pwd),
            role=role, is_active=True,
        ))
    db.commit()


def seed_equipments(db) -> dict:
    """返回 {name: Equipment} 映射，给后面的路线引用"""
    eq_map: dict = {}
    sys_counter: dict = {}
    for sys, crit, name, location, manuf, model in EQUIPMENT_SEEDS:
        existing = db.query(Equipment).filter(Equipment.name == name).first()
        if existing:
            eq_map[name] = existing
            continue
        sys_counter[sys] = sys_counter.get(sys, 0) + 1
        code = generate_equipment_code(sys, sys_counter[sys])
        e = Equipment(
            code=code,
            name=name,
            equipment_system=EquipmentSystem(sys),
            criticality=crit,
            location=location,
            manufacturer=manuf,
            model=model,
            install_date=date(2018, 6, 1),
            status=EquipmentStatus.RUNNING,
            qr_code=f"EQ::{code}",
            health_score=95,
        )
        db.add(e)
        db.flush()
        eq_map[name] = e
    db.commit()
    return eq_map


COMMON_PUMP_CHECKS = [
    {"name": "运行电流", "type": "NUM", "unit": "A", "min": 0, "max": 200},
    {"name": "出口压力", "type": "NUM", "unit": "MPa", "min": 0.5, "max": 16},
    {"name": "轴承温度", "type": "NUM", "unit": "℃", "min": 0, "max": 75},
    {"name": "异响", "type": "BOOL"},
    {"name": "泄漏", "type": "BOOL"},
]
COMMON_FAN_CHECKS = [
    {"name": "电流", "type": "NUM", "unit": "A", "min": 0, "max": 300},
    {"name": "轴承振动", "type": "NUM", "unit": "mm/s", "min": 0, "max": 7.1},
    {"name": "异响", "type": "BOOL"},
]


def seed_routes_and_points(db, eq_map: dict):
    if db.query(InspectionRoute).count() > 0:
        return

    # 路线1：锅炉系统日常巡检
    r1 = InspectionRoute(
        route_no=generate_route_no(1), name="1#机组锅炉日常巡检",
        equipment_system="BOILER", frequency=RouteFrequency.SHIFT,
        estimated_duration=45, is_active=True,
    )
    db.add(r1); db.flush()
    boiler_targets = ["1号锅炉本体", "1号锅炉给水泵", "1号送风机", "1号引风机", "1号一次风机"]
    for i, name in enumerate(boiler_targets, 1):
        if name not in eq_map:
            continue
        items = COMMON_FAN_CHECKS if "风机" in name else (
            COMMON_PUMP_CHECKS if "泵" in name else [
                {"name": "主蒸汽温度", "type": "NUM", "unit": "℃", "min": 535, "max": 545},
                {"name": "主蒸汽压力", "type": "NUM", "unit": "MPa", "min": 16.5, "max": 17.5},
                {"name": "炉膛负压", "type": "NUM", "unit": "Pa", "min": -200, "max": -50},
                {"name": "省煤器入口烟温", "type": "NUM", "unit": "℃", "min": 280, "max": 380},
            ]
        )
        db.add(InspectionPoint(
            point_no=generate_point_no(i),
            route_id=r1.id, equipment_id=eq_map[name].id,
            sequence=i, check_items=items,
            standard=f"按 {name} 设计参数执行",
        ))
    db.flush()

    # 路线2：汽机+发电机日常巡检
    r2 = InspectionRoute(
        route_no=generate_route_no(2), name="1#机组汽机发电机巡检",
        equipment_system="TURBINE", frequency=RouteFrequency.DAILY,
        estimated_duration=60, is_active=True,
    )
    db.add(r2); db.flush()
    turbine_targets = [("1号汽轮机", [
        {"name": "高压缸进汽温度", "type": "NUM", "unit": "℃", "min": 530, "max": 545},
        {"name": "凝汽器真空", "type": "NUM", "unit": "kPa", "min": -100, "max": -90},
        {"name": "推力轴承温度", "type": "NUM", "unit": "℃", "min": 0, "max": 80},
        {"name": "汽缸膨胀", "type": "NUM", "unit": "mm", "min": 0, "max": 50},
    ]), ("1号汽机润滑油泵", COMMON_PUMP_CHECKS), ("1号发电机", [
        {"name": "定子电流", "type": "NUM", "unit": "A", "min": 0, "max": 12000},
        {"name": "定子温度", "type": "NUM", "unit": "℃", "min": 0, "max": 100},
        {"name": "氢压", "type": "NUM", "unit": "MPa", "min": 0.3, "max": 0.45},
        {"name": "功率因数", "type": "NUM", "unit": "", "min": 0.85, "max": 1.0},
    ])]
    next_seq = db.query(InspectionPoint).count() + 1
    for i, (name, items) in enumerate(turbine_targets):
        if name not in eq_map:
            continue
        db.add(InspectionPoint(
            point_no=generate_point_no(next_seq + i),
            route_id=r2.id, equipment_id=eq_map[name].id,
            sequence=i + 1, check_items=items,
            standard=f"按 {name} 运行规程执行",
        ))
    db.flush()

    # 路线3：脱硫脱硝周巡
    r3 = InspectionRoute(
        route_no=generate_route_no(3), name="脱硫脱硝周巡检",
        equipment_system="DESULFUR", frequency=RouteFrequency.WEEKLY,
        estimated_duration=90, is_active=True,
    )
    db.add(r3); db.flush()
    desulf_targets = ["脱硫吸收塔1#", "脱硫浆液循环泵1A", "脱硝SCR反应器1#"]
    next_seq = db.query(InspectionPoint).count() + 1
    for i, name in enumerate(desulf_targets):
        if name not in eq_map:
            continue
        items = COMMON_PUMP_CHECKS if "泵" in name else [
            {"name": "脱硫效率", "type": "NUM", "unit": "%", "min": 95, "max": 100},
            {"name": "出口SO2", "type": "NUM", "unit": "mg/Nm³", "min": 0, "max": 35},
            {"name": "浆液pH", "type": "NUM", "unit": "", "min": 5.0, "max": 5.8},
        ] if "吸收塔" in name else [
            {"name": "出口NOx", "type": "NUM", "unit": "mg/Nm³", "min": 0, "max": 50},
            {"name": "氨逃逸", "type": "NUM", "unit": "ppm", "min": 0, "max": 3},
            {"name": "压差", "type": "NUM", "unit": "Pa", "min": 0, "max": 1200},
        ]
        db.add(InspectionPoint(
            point_no=generate_point_no(next_seq + i),
            route_id=r3.id, equipment_id=eq_map[name].id,
            sequence=i + 1, check_items=items,
            standard=f"按 {name} 环保参数执行",
        ))
    db.commit()


def seed_tasks_and_defects(db):
    if db.query(InspectionTask).count() > 0:
        return

    today = datetime.utcnow().replace(hour=8, minute=0, second=0, microsecond=0)
    routes = db.query(InspectionRoute).all()
    task_idx = 0
    # 一周内每条路线生成多条任务
    for delta in range(-6, 1):
        run_date = today + timedelta(days=delta)
        for r in routes:
            # SHIFT 一天 3 班，DAILY 一天 1 条，WEEKLY 只在周一
            if r.frequency == RouteFrequency.SHIFT:
                slots = [0, 8, 16]
            elif r.frequency == RouteFrequency.DAILY:
                slots = [8]
            else:
                if run_date.weekday() != 0:
                    continue
                slots = [9]
            for h in slots:
                task_idx += 1
                scheduled = run_date.replace(hour=h)
                t = InspectionTask(
                    task_no=generate_task_no(task_idx),
                    route_id=r.id,
                    scheduled_at=scheduled,
                    assigned_to="inspector",
                    status=TaskStatus.PENDING,
                )
                # 历史任务大部分已完成
                if delta < 0:
                    t.status = TaskStatus.COMPLETED
                    t.started_at = scheduled
                    t.completed_at = scheduled + timedelta(minutes=r.estimated_duration)
                    t.executed_by = "inspector"
                db.add(t)
                db.flush()
                # 给一部分历史任务挂正常 record
                if t.status == TaskStatus.COMPLETED:
                    for p in r.points:
                        rec = InspectionRecord(
                            task_id=t.id, point_id=p.id,
                            status=PointStatus.NORMAL,
                            recorded_by="inspector",
                            recorded_at=t.completed_at,
                        )
                        db.add(rec)
    db.commit()

    # 构造若干典型缺陷
    eq_by_name = {e.name: e for e in db.query(Equipment).all()}

    def add_defect(eq_name, title, sev, status, days_ago=0, repair_cost=0, sync_status=None, hazard_no=None, sync_error=None):
        eq = eq_by_name.get(eq_name)
        if not eq:
            return
        seq = (db.query(Defect).count() or 0) + 1
        d = Defect(
            defect_no=generate_defect_no(seq),
            equipment_id=eq.id,
            source=DefectSource.INSPECTION,
            severity=sev, status=status,
            title=title, description=title + "（详细见现场照片）",
            reported_by="inspector",
            reported_at=datetime.utcnow() - timedelta(days=days_ago),
            sla_deadline=datetime.utcnow() + timedelta(hours=24),
        )
        if status in (DefectStatus.ASSIGNED, DefectStatus.IN_REPAIR, DefectStatus.REPAIRED, DefectStatus.CLOSED):
            d.assigned_to = "repairman"
            d.assigned_by = "supervisor"
            d.assigned_at = d.reported_at + timedelta(hours=1)
        if status in (DefectStatus.IN_REPAIR, DefectStatus.REPAIRED, DefectStatus.CLOSED):
            d.repair_started_at = d.assigned_at + timedelta(hours=1)
        if status in (DefectStatus.REPAIRED, DefectStatus.CLOSED):
            d.repair_completed_at = d.repair_started_at + timedelta(hours=4)
            d.repair_notes = "更换密封件 + 复紧螺栓 + 清理积灰。"
            d.repair_cost = repair_cost
        if status == DefectStatus.CLOSED:
            d.verified_by = "supervisor"
            d.verified_at = d.repair_completed_at + timedelta(hours=1)
            d.verify_notes = "运行 24h 复查无异常，关闭。"
            d.closed_at = d.verified_at
        # v2：plant-safety 联动状态
        if sync_status is not None:
            d.safety_sync_status = sync_status
            d.safety_hazard_no = hazard_no
            d.safety_sync_error = sync_error
            if sync_status == "SYNCED":
                d.safety_sync_at = d.reported_at + timedelta(seconds=2)
                d.safety_sync_attempts = 1
            elif sync_status == "FAILED":
                d.safety_sync_attempts = 3
            elif sync_status == "PENDING":
                d.safety_sync_attempts = 1
        elif sev == DefectSeverity.CRITICAL:
            d.safety_sync_status = "SYNCED"
            d.safety_hazard_no = f"HZ-{datetime.utcnow():%Y%m%d}-0001"
            d.safety_sync_at = d.reported_at + timedelta(seconds=2)
            d.safety_sync_attempts = 1
        else:
            d.safety_sync_status = "SKIPPED"
        db.add(d)

    add_defect("1号锅炉给水泵", "出口压力波动且有异响", DefectSeverity.MAJOR, DefectStatus.IN_REPAIR, days_ago=2)
    add_defect("1号送风机", "电流偏高且轴承温度 78℃", DefectSeverity.MAJOR, DefectStatus.NEW, days_ago=0)
    add_defect(
        "1号引风机", "异响严重，疑似叶轮失衡",
        DefectSeverity.CRITICAL, DefectStatus.ASSIGNED, days_ago=1,
        sync_status="SYNCED", hazard_no=f"HZ-{datetime.utcnow():%Y%m%d}-0007",
    )
    add_defect("脱硫浆液循环泵1A", "机封轻微渗漏", DefectSeverity.MINOR, DefectStatus.CLOSED, days_ago=5, repair_cost=850)
    add_defect("化学水处理一级反渗透", "产水电导超标", DefectSeverity.MINOR, DefectStatus.REPAIRED, days_ago=3)
    add_defect("1号汽机润滑油泵", "压力轻微偏低", DefectSeverity.MINOR, DefectStatus.CLOSED, days_ago=8, repair_cost=300)
    # 再补两条用于演示联动状态多样性
    add_defect(
        "2号锅炉本体", "屏式过热器局部超温", DefectSeverity.CRITICAL, DefectStatus.NEW, days_ago=0,
        sync_status="FAILED", sync_error="Connection refused（plant-safety 暂未启动）",
    )
    add_defect(
        "主变压器1#", "瓦斯继电器告警", DefectSeverity.CRITICAL, DefectStatus.ASSIGNED, days_ago=0,
        sync_status="PENDING",
    )
    db.commit()

    # 让一台 CRITICAL 缺陷设备进入 MAINTENANCE
    yh = eq_by_name.get("1号引风机")
    if yh:
        yh.status = EquipmentStatus.MAINTENANCE
        yh.health_score = 70
        db.commit()


def seed_tickets(db):
    if db.query(WorkTicket).count() > 0:
        return
    eq_by_name = {e.name: e for e in db.query(Equipment).all()}
    defect_for_yh = db.query(Defect).filter(Defect.title.like("异响严重%")).first()

    yh = eq_by_name.get("1号引风机")
    sd_pump = eq_by_name.get("脱硫浆液循环泵1A")

    # 工作票 1：和 1号引风机 CRITICAL 缺陷挂钩，已签发
    if yh:
        w1 = WorkTicket(
            ticket_no=generate_work_ticket_no(1),
            ticket_type=WorkTicketType.FIRST,
            defect_id=defect_for_yh.id if defect_for_yh else None,
            equipment_id=yh.id,
            work_content="更换 1#引风机轴承及叶轮动平衡校验",
            risk_notes="高处坠落、机械伤害、误操作合闸",
            safety_measures=[
                {"seq": 1, "measure": "断开 6kV 主开关并悬挂\"禁止合闸\"标识牌", "checked": True,
                 "checked_by": "repairman", "checked_at": (datetime.utcnow() - timedelta(hours=10)).isoformat()},
                {"seq": 2, "measure": "验电后装设接地线", "checked": True,
                 "checked_by": "repairman", "checked_at": (datetime.utcnow() - timedelta(hours=9)).isoformat()},
                {"seq": 3, "measure": "工作区域围栏隔离，设置警示标识", "checked": False},
                {"seq": 4, "measure": "佩戴安全带及防坠器", "checked": False},
            ],
            planned_start=datetime.utcnow() - timedelta(hours=8),
            planned_end=datetime.utcnow() + timedelta(hours=8),
            applicant="supervisor",
            principal="repairman",
            issuer="supervisor",
            team_members=["repairman", "inspector"],
            status=WorkTicketStatus.ISSUED,
            submitted_at=datetime.utcnow() - timedelta(hours=12),
            issued_at=datetime.utcnow() - timedelta(hours=11),
            approval_notes="安全措施合规，同意签发。",
        )
        db.add(w1)

    # 工作票 2：第二种工作票（已归档）
    if sd_pump:
        w2 = WorkTicket(
            ticket_no=generate_work_ticket_no(2),
            ticket_type=WorkTicketType.SECOND,
            equipment_id=sd_pump.id,
            work_content="脱硫浆液循环泵 1A 机封更换",
            risk_notes="浆液飞溅、烫伤",
            safety_measures=[
                {"seq": 1, "measure": "关闭进出口阀门", "checked": True, "checked_by": "repairman",
                 "checked_at": (datetime.utcnow() - timedelta(days=5)).isoformat()},
                {"seq": 2, "measure": "穿戴防腐蚀工作服 + 护目镜", "checked": True, "checked_by": "repairman",
                 "checked_at": (datetime.utcnow() - timedelta(days=5)).isoformat()},
            ],
            applicant="supervisor",
            principal="repairman",
            issuer="supervisor",
            permitter="supervisor",
            status=WorkTicketStatus.CLOSED,
            submitted_at=datetime.utcnow() - timedelta(days=5, hours=2),
            issued_at=datetime.utcnow() - timedelta(days=5, hours=1),
            permitted_at=datetime.utcnow() - timedelta(days=5),
            actual_start=datetime.utcnow() - timedelta(days=5),
            actual_end=datetime.utcnow() - timedelta(days=5, hours=-4),
            completed_at=datetime.utcnow() - timedelta(days=5, hours=-4),
            closed_at=datetime.utcnow() - timedelta(days=4, hours=20),
            closing_notes="设备试运行 24h 正常，工作票收回归档。",
        )
        db.add(w2)
    db.flush()

    # 操作票 1：1#引风机停电操作（已批准，待执行）
    if yh:
        w1 = db.query(WorkTicket).filter(WorkTicket.ticket_no == generate_work_ticket_no(1)).first()
        o1 = OperationTicket(
            ticket_no=generate_operation_ticket_no(1),
            title="1#引风机检修停电操作",
            operation_type=OperationTicketType.POWER_OFF,
            work_ticket_id=w1.id if w1 else None,
            equipment_id=yh.id,
            operator="inspector",
            supervisor="supervisor",
            approver="admin",
            steps=[
                {"seq": 1, "action": "断开 1#引风机 6kV 主开关",
                 "expected": "红灯灭、绿灯亮", "result": "PASS",
                 "executed_by": "inspector",
                 "executed_at": (datetime.utcnow() - timedelta(hours=10)).isoformat()},
                {"seq": 2, "action": "拉开隔离开关并锁定", "expected": "刀闸位置指示在分位",
                 "result": "PASS", "executed_by": "inspector",
                 "executed_at": (datetime.utcnow() - timedelta(hours=9, minutes=50)).isoformat()},
                {"seq": 3, "action": "验电（高压）", "expected": "三相均无电压", "result": "PASS",
                 "executed_by": "inspector",
                 "executed_at": (datetime.utcnow() - timedelta(hours=9, minutes=45)).isoformat()},
                {"seq": 4, "action": "装设接地线 1 组", "expected": "接地良好", "result": None},
                {"seq": 5, "action": "悬挂\"禁止合闸，有人工作\"标识牌", "expected": "标识就位",
                 "result": None},
            ],
            status=OperationTicketStatus.EXECUTING,
            reviewed_at=datetime.utcnow() - timedelta(hours=12),
            approved_at=datetime.utcnow() - timedelta(hours=11),
            started_at=datetime.utcnow() - timedelta(hours=10),
        )
        db.add(o1)
    db.commit()


SPARE_PARTS_SEEDS = [
    # (name, spec, unit, category, stock, min, price, location)
    ("深沟球轴承", "6312-2RS", "套", "轴承", 24, 8, 380.00, "备件库 A-01"),
    ("圆柱滚子轴承", "NU313", "套", "轴承", 12, 4, 620.00, "备件库 A-02"),
    ("机械密封", "104-50mm", "套", "密封件", 8, 5, 1280.00, "备件库 B-03"),
    ("O型密封圈", "Φ80×3.5", "件", "密封件", 200, 50, 8.00, "备件库 B-05"),
    ("电机润滑脂", "Mobil XHP-222", "kg", "油料", 35, 10, 95.00, "油品库 C-12"),
    ("汽轮机油", "ISO VG 46", "桶(200L)", "油料", 6, 2, 4200.00, "油品库 C-01"),
    ("接触器", "施耐德 LC1-D80", "个", "电子件", 3, 5, 580.00, "电气库 D-04"),  # 低库存
    ("热电偶", "K 型 0-1200℃", "支", "电子件", 18, 10, 220.00, "电气库 D-09"),
    ("压力变送器", "EJA430A 0-16MPa", "套", "电子件", 4, 3, 5800.00, "电气库 D-15"),
    ("扭矩扳手", "10-100N·m", "把", "工具", 5, 2, 1200.00, "工具室 E-01"),
    ("不锈钢闸阀", "DN50 304", "个", "管阀", 2, 4, 480.00, "管材库 F-08"),  # 低库存
    ("焊接弯头", "DN100 90°", "个", "管阀", 30, 12, 65.00, "管材库 F-12"),
]


def seed_spare_parts(db):
    if db.query(SparePart).count() > 0:
        return
    for i, (name, spec, unit, cat, stock, mn, price, loc) in enumerate(SPARE_PARTS_SEEDS, 1):
        sp = SparePart(
            code=generate_spare_part_code(i),
            name=name, spec=spec, unit=unit, category=cat,
            stock_qty=stock, min_qty=mn, unit_price=price,
            location=loc, supplier="电厂物资统一采购",
        )
        db.add(sp)
    db.commit()

    # 配几条出入库流水（让流水页演示）
    bearing = db.query(SparePart).filter(SparePart.name == "深沟球轴承").first()
    seal = db.query(SparePart).filter(SparePart.name == "机械密封").first()
    if bearing:
        db.add(StockMovement(
            spare_part_id=bearing.id, movement_type=StockMovementType.IN,
            qty=24, operator="admin", notes="2026 年 5 月入库",
            created_at=datetime.utcnow() - timedelta(days=10),
        ))
    if seal:
        defect = db.query(Defect).filter(Defect.title.like("机封轻微渗漏%")).first()
        db.add(StockMovement(
            spare_part_id=seal.id, movement_type=StockMovementType.OUT,
            qty=2, defect_id=defect.id if defect else None,
            operator="repairman", notes="脱硫泵机封更换",
            created_at=datetime.utcnow() - timedelta(days=5),
        ))
    db.commit()


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_users(db)
        eq_map = seed_equipments(db)
        seed_routes_and_points(db, eq_map)
        seed_tasks_and_defects(db)
        seed_tickets(db)
        seed_spare_parts(db)
        print("[seed] 完成：")
        print(f"  users={db.query(User).count()}")
        print(f"  equipments={db.query(Equipment).count()}")
        print(f"  routes={db.query(InspectionRoute).count()} / points={db.query(InspectionPoint).count()}")
        print(f"  tasks={db.query(InspectionTask).count()} / records={db.query(InspectionRecord).count()}")
        print(f"  defects={db.query(Defect).count()}")
        print(f"  work_tickets={db.query(WorkTicket).count()} / operation_tickets={db.query(OperationTicket).count()}")
        print(f"  spare_parts={db.query(SparePart).count()} / movements={db.query(StockMovement).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
