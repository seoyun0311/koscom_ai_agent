import requests
import zipfile, io
import xml.etree.ElementTree as ET

API_KEY = "Y402ddb54a2b263ae08190da33373b2c200474d63"

z = requests.get(
    "https://opendart.fss.or.kr/api/corpCode.xml",
    params={"crtfc_key": API_KEY},
).content

with zipfile.ZipFile(io.BytesIO(z)) as zf:
    xml = zf.read("CORPCODE.xml")

root = ET.fromstring(xml)

def find_corp(name):
    for el in root.iter("list"):
        if (el.findtext("corp_name") or "").strip() == name:
            return {
                "corp_name": el.findtext("corp_name"),
                "corp_code": el.findtext("corp_code"),
                "stock_code": el.findtext("stock_code"),
                "modify_date": el.findtext("modify_date"),
            }

print(find_corp("하나금융지주"))
print(find_corp("NH투자증권"))
