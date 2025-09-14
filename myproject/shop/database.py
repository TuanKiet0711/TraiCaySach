# database.py
from pymongo import MongoClient

# Kết nối MongoDB. Nếu bạn dùng Atlas, thay chuỗi host bên dưới bằng URI Atlas.
client = MongoClient("mongodb://localhost:27017/", uuidRepresentation="standard")

# Chọn database
db = client["TraiCay"]

# Giờ bạn có db.tai_khoan, db.san_pham, db.danh_muc, db.gio_hang, db.don_hang
# Các collection
tai_khoan = db["tai_khoan"]
danh_muc  = db["danh_muc"]
san_pham  = db["san_pham"]
gio_hang  = db["gio_hang"]
don_hang  = db["don_hang"]