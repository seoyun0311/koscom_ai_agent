import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db.influx import write_bank_reserve

write_bank_reserve("KB Bank", 123000000)
write_bank_reserve("Shinhan Bank", 88000000)

print("✅ InfluxDB 실데이터 저장 완료")