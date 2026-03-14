import sys
import logging
import json
import os

REQUIRED_PACKAGES = ["bless"]

def check_dependencies():
    """
    检查必要的依赖包
    """
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        logging.error("缺少以下依赖:")
        for pkg in missing:
            logging.error(f"    - {pkg}")
        logging.error(f"请运行以下命令安装: pip install {' '.join(missing)}")
        sys.exit(1)

check_dependencies()

import asyncio
import struct
import math
import time
from bless import (
    BlessServer,
    BlessGATTCharacteristic,
    GATTCharacteristicProperties,
    GATTAttributePermissions
)
from bike_client import BikeClient

def load_config():
    """
    加载配置文件
    """
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    default_config = {
        "log_level": "INFO",
        "bluetooth_device_name": "Bike_FTMS",
        "max_resistance_level": 24,
        "base_resistance_level": 6.0,
        "grade_effect_uphill": 1.5,
        "grade_effect_downhill": 1.0,
        "wind_effect": 0.05,
        "crr_effect": 500,
        "resistance_throttle_interval": 5.0,
        "ftms_update_interval": 1.0
    }
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            for key in default_config:
                if key not in config:
                    config[key] = default_config[key]
            return config
    except FileNotFoundError:
        logging.warning("未找到 config.json，使用默认配置")
        return default_config
    except json.JSONDecodeError as e:
        logging.error(f"config.json 格式错误: {e}")
        return default_config

CONFIG = load_config()

logging.basicConfig(level=getattr(logging, CONFIG["log_level"].upper(), logging.INFO))
logger = logging.getLogger("FTMS_Bike")

# --- FTMS 规范 UUID ---
FTMS_UUID = "00001826-0000-1000-8000-00805f9b34fb"
FTM_FEATURE_UUID = "00002acc-0000-1000-8000-00805f9b34fb"
INDOOR_BIKE_DATA_UUID = "00002ad2-0000-1000-8000-00805f9b34fb"
FTM_CONTROL_POINT_UUID = "00002ad9-0000-1000-8000-00805f9b34fb"
FTM_STATUS_UUID = "00002ada-0000-1000-8000-00805f9b34fb"
SUPPORTED_RESISTANCE_LEVEL_RANGE_UUID = "00002ad6-0000-1000-8000-00805f9b34fb"

class SmartIndoorBike:
    def __init__(self, server: BlessServer, bike_client: BikeClient):
        self.server = server
        self.bike_client = bike_client
        # 将默认状态改为 True，连接后立刻开始广播数据
        self.is_started = True
        self.base_speed_kmh = 20.0
        self.base_cadence_rpm = 90.0
        self.base_power_w = 150
        
        self.distance_m = 0
        self.resistance_level = 10.0
        self.calories = 0
        self.elapsed_sec = 0
        self.tick = 0  # 增加一个时钟 tick 用于生成正弦波动
        self.current_hw_level = -1  # 记录当前已设置到单车的硬件档位
        self.last_res_send_time = 0  # 记录上次发送阻力指令的时间
    
    # def map_resistance_to_hardware(self, ftms_val):
    #     """将 FTMS 的 0.0-100.0 映射到硬件 1-24"""
    #     # 限制范围并计算
    #     clamped_val = max(0, min(100, ftms_val))
    #     hw_level = round((clamped_val / 100.0) * 23) + 1
    #     return hw_level
    
    # def map_hardware_to_ftms(self, hw_level):
    #     """将硬件 1-24 映射到 FTMS 的 0.0-100.0"""
    #     clamped_level = max(1, min(24, hw_level))
    #     ftms_val = ((clamped_level - 1) / 23.0) * 100.0
    #     return round(ftms_val, 1) # 保留一位小数
    
    def calculate_approx_resistance(self, grade_pct, wind_speed_mps, crr):
        """
        基于经验系数的阻力近似拟合
        :param grade_pct: 坡度百分比 (例如 3.5)
        :param wind_speed_mps: 风速 m/s (假设负数为逆风，正数为顺风)
        :param crr: 滚动阻力系数 (普通柏油路通常在 0.004 左右)
        """
        base_level = CONFIG["base_resistance_level"]
        
        if grade_pct > 0:
            grade_effect = grade_pct * CONFIG["grade_effect_uphill"]
        else:
            grade_effect = grade_pct * CONFIG["grade_effect_downhill"]
            
        wind_effect = -wind_speed_mps * CONFIG["wind_effect"]
        road_effect = (crr - 0.004) * CONFIG["crr_effect"]
        
        target_level = base_level + grade_effect + wind_effect + road_effect
        
        final_hw_level = max(1, min(CONFIG["max_resistance_level"], round(target_level)))
        
        logger.debug(f"坡度={grade_pct}%, 风速={wind_speed_mps}m/s, 路面={crr}, 目标档位={final_hw_level}")
        return final_hw_level
        
    def read_request(self, characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
        logger.debug(f"Reading {characteristic.uuid}")
        return characteristic.value

    def write_request(self, characteristic: BlessGATTCharacteristic, value: bytearray, **kwargs):
        if characteristic.uuid == FTM_CONTROL_POINT_UUID:
            self.handle_control_point(value)
            
    def handle_control_point(self, value: bytearray):
        """处理 App 发送的 Control Point 指令"""
        if len(value) < 1: return
        op_code = value[0]
        response_code = 0x01 # 0x01 = Success [cite: 806]
        
        # 0x00: Request Control [cite: 592]
        if op_code == 0x00:
            logger.info("App requested control.")
            
        # 0x07: Start or Resume 
        elif op_code == 0x07:
            self.is_started = True
            logger.info("Bike Started.")
            asyncio.create_task(self.bike_client.start_bike()) # 控制物理单车
            
        # 0x08: Stop or Pause [cite: 617]
        elif op_code == 0x08:
            self.is_started = False
            logger.info("Bike Stopped.")
            asyncio.create_task(self.bike_client.stop_bike()) # 控制物理单车
            
        # 0x03, 0x04: 不支持的控制命令
        elif op_code in (0x03, 0x04):
            logger.info(f"OpCode {op_code:#02x} not supported in this build; ignoring.")
            response_code = 0x02  # Op Code not supported
            
        # 0x11: Set Indoor Bike Simulation Parameters
        elif op_code == 0x11:
            logger.debug("收到控制命令 [0x11] 设置室内单车模拟参数")
            wind_raw, grade_raw, crr_raw, cw_raw = struct.unpack('<hhBB', value[1:7])
            grade_pct = grade_raw * 0.01
            wind_mps = wind_raw * 0.01
            crr = crr_raw * 0.0001
            
            # 调用简洁的近似拟合函数 (忽略 cw)
            hw_level = self.calculate_approx_resistance(grade_pct, wind_mps, crr)
            
            # --- 关键过滤与节流逻辑 ---
            current_time = time.monotonic()
            time_passed = current_time - self.last_res_send_time
            
            # 条件 1: 档位必须有变化
            if hw_level == self.current_hw_level:
                logger.debug(f"[*] 阻力值已为 {hw_level}，无需发送指令")
                return

            # 条件 2: 距离上次发送必须超过 5 秒
            if time_passed < CONFIG["resistance_throttle_interval"]:
                logger.debug(f"[跳过] 档位虽变为 {hw_level}，但距离上次发送仅 {time_passed:.1f}s (未满{CONFIG['resistance_throttle_interval']}s)")
                return
            
            self.current_hw_level = hw_level
            self.last_res_send_time = current_time
            asyncio.create_task(self.bike_client.set_resistance(hw_level, CONFIG["max_resistance_level"]))
            logger.info(f"[√] 满足 {CONFIG['resistance_throttle_interval']}s 间隔且档位改变，发送新指令: 阻力={hw_level}")
            
        else:
            response_code = 0x02 # 0x02 = Op Code not supported [cite: 809]

        # 构造 Indication 响应: OpCode(0x80) + 收到指令的OpCode + 结果状态 [cite: 803]
        response = bytearray([0x80, op_code, response_code])
        self.server.get_characteristic(FTM_CONTROL_POINT_UUID).value = response
        self.server.update_value(FTMS_UUID, FTM_CONTROL_POINT_UUID)

    async def broadcast_data_loop(self):
        """将物理单车的数据广播"""
        while True:
            # 直接从物理单车客户端获取最新数据
            real_data = self.bike_client.get_current_data()
            
            if self.is_started and real_data:
                # 从真实数据中获取值，如果没有则使用默认值
                speed_kmh = real_data.get("speed", 0.0)
                cadence_rpm = real_data.get("cadence", 0)
                power_w = real_data.get("power", 0)
                resistance_level = real_data.get("resistance", 10)
                distance_m = real_data.get("distance", 0)
                calories = real_data.get("calories", 0)
                elapsed_sec = real_data.get("duration", 0)

                # --- 重新定义 Flags ---
                # Flags bits: Instantaneous Cadence (bit2), Resistance Level Present (bit5), Instant Power Present (bit6)
                # (1<<2) + (1<<5) + (1<<6) -> 0x64
                flags = 0x0064

                # 转换原始值
                speed_raw = int(speed_kmh * 100)      # UINT16, 0.01 km/h
                cadence_raw = int(cadence_rpm * 2)    # UINT16, 0.5 1/min
                res_raw = int(resistance_level)       # SINT16, 精度 1 (FTMS 标准)
                pwr_raw = int(power_w)                # SINT16, 1W

                # --- 严格按照 FTMS v1.0 顺序手动拼接 ---
                payload = bytearray()
                payload += struct.pack('<H', flags)           # [0-1] Flags
                payload += struct.pack('<H', speed_raw)       # [2-3] Speed
                payload += struct.pack('<H', cadence_raw)     # [4-5] Cadence
                payload += struct.pack('<h', res_raw)         # [6-7] Resistance
                payload += struct.pack('<h', pwr_raw)         # [8-9] Power

                if len(payload) == 10:
                    try:
                        self.server.get_characteristic(INDOOR_BIKE_DATA_UUID).value = payload
                        self.server.update_value(FTMS_UUID, INDOOR_BIKE_DATA_UUID)
                        logger.debug(f"Broadcast: Spd={speed_kmh:.1f}, Cad={cadence_rpm:.1f}, Pwr={power_w}, Res={resistance_level}")
                    except Exception as e:
                        logger.error(f"Notify Error: {e}")
                
            await asyncio.sleep(CONFIG["ftms_update_interval"])

async def main():
    loop = asyncio.get_event_loop()
    
    bike = BikeClient()
    
    server = BlessServer(name=CONFIG["bluetooth_device_name"], loop=loop)
    ftms_bike = SmartIndoorBike(server, bike)
    server.read_request_func = ftms_bike.read_request
    server.write_request_func = ftms_bike.write_request

    await server.add_new_service(FTMS_UUID)
    
    # Feature 值：Bit 1 (Cadence), Bit 6 (Resistance), Bit 14 (Power)
    feature_val = 0x00004082
    # Target Features:  Bit 13 (Simulation)
    target_val = 0x00002000
    feature_payload = struct.pack('<I', feature_val) + struct.pack('<I', target_val)
    
    await server.add_new_characteristic(
        FTMS_UUID, FTM_FEATURE_UUID,
        GATTCharacteristicProperties.read, feature_payload, GATTAttributePermissions.readable
    )

    # 2. 预留 10 字节初始长度，防止被系统截断
    await server.add_new_characteristic(
        FTMS_UUID, INDOOR_BIKE_DATA_UUID,
        GATTCharacteristicProperties.notify, bytearray([0]*10), GATTAttributePermissions.readable
    )

    # 3. 必须添加 Status 特征 (0x2ADA)
    await server.add_new_characteristic(
        FTMS_UUID, FTM_STATUS_UUID,
        GATTCharacteristicProperties.notify, bytearray([0x00]), GATTAttributePermissions.readable
    )

    # 4. 控制点 (0x2AD9)
    await server.add_new_characteristic(
        FTMS_UUID, FTM_CONTROL_POINT_UUID,
        GATTCharacteristicProperties.write | GATTCharacteristicProperties.indicate,
        bytearray([0x00]),
        GATTAttributePermissions.writeable
    )

    # 5. Supported Resistance Level Range (0x2AD6)
    # 最小值: 0.0, 最大值: 100.0, 最小增量: 4.3 (100/23 ≈ 4.34)
    # 精度为 0.1，所以需要乘以 10
    min_res = 0
    max_res = 1000
    min_inc = int(1000 / (CONFIG["max_resistance_level"] - 1))
    resistance_range_payload = struct.pack('<hhH', min_res, max_res, min_inc)
    await server.add_new_characteristic(
        FTMS_UUID, SUPPORTED_RESISTANCE_LEVEL_RANGE_UUID,
        GATTCharacteristicProperties.read, resistance_range_payload, GATTAttributePermissions.readable
    )

    await server.start()
    logger.info("FTMS Indoor Bike started! Connect via FTMS App.")
    
    await asyncio.gather(
        bike.run_client(),
        ftms_bike.broadcast_data_loop()
    )

if __name__ == "__main__":
    asyncio.run(main())