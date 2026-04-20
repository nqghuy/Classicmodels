# ClassicModels Analytics Website

Ứng dụng web phân tích CSDL ClassicModels với:

- RESTful API dùng Python chuẩn (`http.server`).
- SQLite database tự sinh từ file `mysqlsampledatabase.sql`.
- Lớp truy cập dữ liệu kiểu ORM nhẹ: `Model`, `Query`, `Customer`, `Order`, `Product`, `Payment`, `OrderDetail`.
- Dashboard thống kê, tìm kiếm, báo cáo, chart và pivot table theo khách hàng, thời gian, mặt hàng.
- Chatbot dùng Gemini API qua backend endpoint `POST /api/chat`.

## Chạy ứng dụng

```bash
python3 server.py
```

Mở trình duyệt:

```text
http://localhost:8000
```

Để bật chatbot Gemini, chạy server với biến môi trường:

```bash
GEMINI_API_KEY='your_gemini_api_key' python3 server.py
```

Hoặc tạo file `.env` local:

```bash
cp .env.example .env
```

Sau đó sửa `GEMINI_API_KEY` trong `.env` và chạy:

```bash
python3 server.py
```

Không đưa API key vào `index.html` hoặc `app.js` vì frontend có thể bị xem mã nguồn trên trình duyệt. File `.env` đã được thêm vào `.gitignore`.

Nếu cổng `8000` bận:

```bash
PORT=8020 python3 server.py
```

Mở:

```text
http://localhost:8020
```

## RESTful API

### Metadata

```http
GET /api/meta
```

Trả về danh sách khách hàng, quốc gia, trạng thái đơn hàng, dòng sản phẩm, năm và khoảng ngày dữ liệu.

### Thống kê tổng quan

```http
GET /api/stats
GET /api/stats?country=USA&status=Shipped&product_line=Classic%20Cars
```

Trả về tổng đơn hàng, khách hàng, sản phẩm, doanh thu, số lượng bán, thanh toán và giá trị đơn trung bình.

### Xu hướng doanh thu theo thời gian

```http
GET /api/revenue/trend
GET /api/revenue/trend?group=year
GET /api/revenue/trend?start_date=2004-01-01&end_date=2004-12-31
```

Mặc định nhóm theo tháng. Có thể nhóm theo năm bằng `group=year`.

### Báo cáo trạng thái đơn hàng

```http
GET /api/reports/status
```

Trả về doanh thu và số đơn theo trạng thái: `Shipped`, `Cancelled`, `Disputed`, `On Hold`, ...

### Báo cáo mặt hàng

```http
GET /api/reports/products
```

Trả về doanh thu, số lượng và số sản phẩm theo `productLine`.

### Top khách hàng

```http
GET /api/reports/top-customers
GET /api/reports/top-customers?limit=20
```

Trả về khách hàng có doanh thu cao nhất.

### Tìm kiếm đơn hàng

```http
GET /api/orders
GET /api/orders?q=Ferrari
GET /api/orders?country=France&status=Shipped&product_line=Classic%20Cars
```

Hỗ trợ tìm theo tên khách hàng, quốc gia, thành phố, mã đơn hàng, trạng thái, tên sản phẩm và dòng sản phẩm.

### Tìm kiếm khách hàng

```http
GET /api/customers
GET /api/customers?q=Mini&country=USA
```

### Pivot table

```http
GET /api/pivot?row=country&col=year&metric=revenue
GET /api/pivot?row=customer&col=month&metric=orders
GET /api/pivot?row=productLine&col=year&metric=quantity
```

`row` và `col` hỗ trợ:

- `customer`
- `country`
- `year`
- `month`
- `productLine`
- `product`
- `status`

`metric` hỗ trợ:

- `revenue`
- `orders`
- `quantity`
- `customers`

### Chatbot Gemini

```http
POST /api/chat
Content-Type: application/json

{
  "message": "Which product line has the highest revenue?",
  "history": []
}
```

Endpoint này lấy context thống kê từ REST API/SQLite, ghép vào prompt và gọi Gemini server-side bằng `GEMINI_API_KEY`.

## File chính

- `server.py`: REST API, ORM-style layer, SQLite migration/import từ SQL dump.
- `index.html`: giao diện dashboard.
- `app.js`: frontend gọi REST API, render chart, report, search, pivot và chatbot.
- `styles.css`: giao diện responsive.
- `mysqlsampledatabase.sql`: dữ liệu ClassicModels gốc.
- `classicmodels.sqlite`: database tự sinh khi chạy server.
