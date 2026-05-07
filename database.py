import logging
import psycopg2
from psycopg2.extras import DictCursor
from config import DB_CONFIG, DINGTALK_CONFIG, MANAGER_MAPPING
from notice import DingTalkRobot

logger = logging.getLogger(__name__)


def get_connection():
    """获取数据库连接"""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.set_client_encoding('UTF8')
    return conn

def init_db():
    """初始化数据库表结构 (根据 PRD 设计)
    注意：如果表已存在，此操作会删除旧表（及旧数据）并重新创建。
    """
    drop_sql = "DROP TABLE IF EXISTS logistics_shipments CASCADE;"

    create_sql = """
    CREATE TABLE logistics_shipments (
        shipment_id VARCHAR(255) PRIMARY KEY,
        tracking_no VARCHAR(255),
        forwarder VARCHAR(255),
        shop_name VARCHAR(255),
        site VARCHAR(50),
        fba_id VARCHAR(255),
        fba_warehouse VARCHAR(255),
        manager_name VARCHAR(255),
        status VARCHAR(255),
        latest_info TEXT,
        etd DATE,
        eta DATE,
        signed_at DATE,
        vessel_voyage VARCHAR(255),
        is_inspected BOOLEAN DEFAULT FALSE,
        raw_full_trace TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(drop_sql)
        cur.execute(create_sql)
        conn.commit()
        logger.info("数据库表已重置（旧表已删除，新表已创建）。")
    except Exception as e:
        logger.error(f"数据库操作失败: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def upsert_shipment(data, conn=None):
    """插入或更新单条数据，支持外部传入连接"""
    close_after = conn is None
    if conn is None:
        conn = get_connection()
    cur = conn.cursor()

    sql = """
    INSERT INTO logistics_shipments (
        shipment_id, tracking_no, forwarder, shop_name, site,
        fba_id, fba_warehouse, manager_name, status, latest_info, etd, eta, signed_at, vessel_voyage, is_inspected
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (shipment_id) DO UPDATE SET
        tracking_no = EXCLUDED.tracking_no,
        forwarder = EXCLUDED.forwarder;
    """

    try:
        cur.execute(sql, (
            data.get('shipment_id'), data.get('tracking_no'), data.get('forwarder'),
            data.get('shop_name'), data.get('site'), data.get('fba_id'),
            data.get('fba_warehouse'), data.get('manager_name'),
            data.get('status'), data.get('latest_info'), data.get('etd'), data.get('eta'),
            data.get('signed_at'), data.get('vessel_voyage'), data.get('is_inspected', False)
        ))
        if close_after:
            conn.commit()
    except Exception as e:
        logger.error(f"数据插入失败: {e}")
        conn.rollback()
    finally:
        cur.close()
        if close_after:
            conn.close()

def batch_upsert_shipments(data_list):
    """批量插入或更新数据，使用单个数据库连接"""
    if not data_list:
        return

    conn = get_connection()
    cur = conn.cursor()

    sql = """
    INSERT INTO logistics_shipments (
        shipment_id, tracking_no, forwarder, shop_name, site,
        fba_id, fba_warehouse, manager_name, status, latest_info, etd, eta, signed_at, vessel_voyage, is_inspected
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (shipment_id) DO UPDATE SET
        tracking_no = EXCLUDED.tracking_no,
        forwarder = EXCLUDED.forwarder;
    """

    try:
        for data in data_list:
            cur.execute(sql, (
                data.get('shipment_id'), data.get('tracking_no'), data.get('forwarder'),
                data.get('shop_name'), data.get('site'), data.get('fba_id'),
                data.get('fba_warehouse'), data.get('manager_name'),
                data.get('status'), data.get('latest_info'), data.get('etd'), data.get('eta'),
                data.get('signed_at'), data.get('vessel_voyage'), data.get('is_inspected', False)
            ))
        conn.commit()
        logger.info(f"批量导入完成，共 {len(data_list)} 条。")
    except Exception as e:
        logger.error(f"批量插入失败: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def get_pending_tasks():
    """获取需要爬取的任务 (status != '签收')"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    sql = "SELECT * FROM logistics_shipments WHERE (status != '签收' OR status IS NULL) AND tracking_no IS NOT NULL AND (latest_info != 'Done' OR latest_info IS NULL)"
    cur.execute(sql)
    rows = cur.fetchall()

    cur.close()
    conn.close()
    return rows

def _status_changed(new_info, old_info):
    """判断物流状态是否真正发生变化"""
    if not new_info:
        return False
    if old_info is None:
        return True
    new_status = new_info.split('————')[0].strip()
    old_status = old_info.split('————')[0].strip()
    return new_status != old_status

def update_tracking_info(shipment_id, result, bot=None):
    """爬虫爬完后，更新数据库（仅更新有值的字段）"""
    conn = get_connection()
    cur = conn.cursor()

    new_latest_info = result.get('latest_info')

    # --- 对比逻辑 ---
    try:
        check_sql = "SELECT latest_info, manager_name, tracking_no, shop_name FROM logistics_shipments WHERE shipment_id = %s"
        cur.execute(check_sql, (shipment_id,))
        row = cur.fetchone()

        if row:
            old_latest_info = row[0]
            manager_name = row[1]
            tracking_no = row[2]
            shop_name = row[3]
            logger.info(f"对比物流状态: {new_latest_info} vs {old_latest_info}")

            if _status_changed(new_latest_info, old_latest_info):
                user_id = MANAGER_MAPPING.get(manager_name)
                if user_id:
                    if bot is None:
                        bot = DingTalkRobot(
                            DINGTALK_CONFIG['app_key'],
                            DINGTALK_CONFIG['app_secret'],
                            DINGTALK_CONFIG['robot_code']
                        )
                    msg = (
                        f"## 🔔 物流状态更新\n"
                        f"单号: {tracking_no}\n"
                        f"店铺： {shop_name}\n"
                        f"发货ID： {shipment_id}\n"
                        f"最新状态： {new_latest_info}\n"
                        f"*请及时关注物流动态*"
                    )
                    logger.info(f"发送钉钉消息给 {manager_name} ({user_id}): {msg}")
                    # bot.send_private_message(user_id, msg)
                else:
                    logger.warning(f"未找到负责人 {manager_name} 对应的钉钉 ID")

    except Exception as e:
        logger.error(f"对比物流状态时出错: {e}")

    # 定义所有可能需要更新的字段映射
    update_fields = {
        'status': result.get('status'),
        'latest_info': result.get('latest_info'),
        'raw_full_trace': result.get('trace'),
        'vessel_voyage': result.get('voyage_info'),
        'etd': result.get('sail_time'),
        'eta': result.get('arrive_time'),
        'signed_at': result.get('sign_time'),
        'is_inspected': result.get('is_inspected')
    }

    set_clauses = []
    values = []

    for db_column, value in update_fields.items():
        if value:
            set_clauses.append(f"{db_column} = %s")
            values.append(value)

    if not set_clauses:
        logger.info(f"ID {shipment_id} 无有效数据更新")
        cur.close()
        conn.close()
        return

    set_clause = ", ".join(set_clauses) + ", updated_at = CURRENT_TIMESTAMP"
    sql = f"UPDATE logistics_shipments SET {set_clause} WHERE shipment_id = %s"

    try:
        cur.execute(sql, values + [shipment_id])
        conn.commit()
        logger.info(f"ID {shipment_id} 更新成功，更新了字段: {', '.join([part.split(' = ')[0] for part in set_clauses])}")
    except Exception as e:
        logger.error(f"ID {shipment_id} 更新数据库失败: {e}")
    finally:
        cur.close()
        conn.close()
