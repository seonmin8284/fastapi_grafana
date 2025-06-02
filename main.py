from fastapi import FastAPI, Request, WebSocket
from kafka import KafkaProducer
import json
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import start_http_server, Gauge, Counter, REGISTRY
import threading
import random
from fastapi import Body
from fastapi.middleware.cors import CORSMiddleware
import time
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
import httpx
from starlette.middleware.base import BaseHTTPMiddleware
import websockets
import asyncio
from starlette.websockets import WebSocketDisconnect

app = FastAPI()

# CORS 설정 업데이트 - WebSocket 지원 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    allow_origin_regex=".*"
)

# X-Frame-Options 제거 미들웨어
class RemoveXFrameOptionsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if "x-frame-options" in response.headers:
            del response.headers["x-frame-options"]
        return response

app.add_middleware(RemoveXFrameOptionsMiddleware)

# Instrumentator 설정
Instrumentator().instrument(app).expose(app)

# Kafka Producer를 전역 변수로 선언
producer = None

try:
    # Kafka Producer 생성 시도
    producer = KafkaProducer(
        bootstrap_servers='kafka:9092',
        value_serializer=lambda x: json.dumps(x).encode('utf-8')
    )
except Exception as e:
    print(f"Failed to connect to Kafka: {e}")

# 커스텀 메트릭
transaction_count = Counter('transaction_count', 'Total number of transactions processed')
transaction_amount = Gauge('transaction_amount', 'Transaction amount in KRW')
transaction_success = Counter('transaction_success', 'Number of successful transactions')
transaction_failure = Counter('transaction_failure', 'Number of failed transactions')
transaction_processing_time = Gauge('transaction_processing_time', 'Transaction processing time in seconds')

# 안전한 헤더만 전달하기 위한 함수
def safe_headers(headers: dict) -> dict:
    # 전달해도 안전한 헤더들
    safe_header_names = {
        "content-type",
        "cache-control",
        "expires",
        "etag",
        "last-modified",
    }
    headers = {
        k.lower(): v 
        for k, v in headers.items() 
        if k.lower() in safe_header_names
    }
    
    # X-Frame-Options 헤더가 있다면 제거
    headers.pop("x-frame-options", None)
    return headers

@app.get("/")
async def proxy_grafana():
    try:
        # 새로운 대시보드 URL로 리다이렉트
        grafana_url = "http://localhost:3000/d/fastapi-metrics/fastapi-metrics-dashboard?orgId=1&refresh=5s"
        headers = {
            "X-WEBAUTH-USER": "admin",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            print(f"Requesting Grafana dashboard at {grafana_url}")
            r = await client.get(grafana_url, headers=headers, follow_redirects=True)
            
            # content-type 헤더 안전하게 처리
            media_type = r.headers.get("content-type", "text/html").split(";")[0].strip()
            
            return Response(
                content=r.content,
                status_code=r.status_code,
                media_type=media_type,
                headers=safe_headers(dict(r.headers))
            )
    except Exception as e:
        print(f"❌ Failed to connect to Grafana: {e}")
        return Response(
            content="Grafana 연결 실패",
            status_code=500,
            media_type="text/plain"
        )

# @app.get("/{path:path}")
# async def proxy_all(path: str, request: Request):
#     try:
#         grafana_url = f"http://localhost:3000/{path}"
        
#         # 원본 요청에서 안전한 헤더만 추출하고 인증 헤더 추가
#         headers = {
#             k: v for k, v in request.headers.items()
#             if k.lower() not in ["host", "connection", "content-length"]
#         }
#         headers.update({
#             "X-WEBAUTH-USER": "admin",
#             "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
#             "Accept-Encoding": "gzip, deflate, br",
#             "Connection": "keep-alive",
#             "Cache-Control": "no-cache"
#         })
        
#         async with httpx.AsyncClient(timeout=10.0) as client:
#             print(f"Proxying request to Grafana: {grafana_url}")
#             r = await client.get(
#                 grafana_url,
#                 headers=headers,
#                 params=dict(request.query_params),
#                 follow_redirects=True
#             )
            
#             # content-type 헤더 안전하게 처리
#             media_type = r.headers.get("content-type", "text/html").split(";")[0].strip()
            
#             # 스트리밍 응답이 필요한 경우 (예: 이벤트 스트림)
#             if media_type == "text/event-stream":
#                 return StreamingResponse(
#                     content=r.iter_bytes(),
#                     media_type=media_type,
#                     headers=safe_headers(dict(r.headers))
#                 )
            
#             return Response(
#                 content=r.content,
#                 status_code=r.status_code,
#                 media_type=media_type,
#                 headers=safe_headers(dict(r.headers))
#             )
#     except Exception as e:
#         print(f"❌ Failed to proxy request to Grafana: {e}")
#         return Response(
#             content="Grafana 프록시 실패",
#             status_code=500,
#             media_type="text/plain"
#         )

@app.post("/{path:path}")
async def proxy_all_post(path: str, request: Request):
    try:
        grafana_url = f"http://localhost:3000/{path}"
        
        # 요청 본문 읽기
        body = await request.body()
        
        # 원본 요청에서 안전한 헤더만 추출하고 인증 헤더 추가
        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ["host", "connection", "content-length"]
        }
        headers.update({
            "X-WEBAUTH-USER": "admin",
            "Accept": "application/json",
            "Content-Type": request.headers.get("content-type", "application/json"),
            "Connection": "keep-alive",
            "Cache-Control": "no-cache"
        })
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            print(f"Proxying POST request to Grafana: {grafana_url}")
            r = await client.post(
                grafana_url,
                headers=headers,
                content=body,
                params=dict(request.query_params),
                follow_redirects=True
            )
            
            # content-type 헤더 안전하게 처리
            media_type = r.headers.get("content-type", "application/json").split(";")[0].strip()
            
            return Response(
                content=r.content,
                status_code=r.status_code,
                media_type=media_type,
                headers=safe_headers(dict(r.headers))
            )
    except Exception as e:
        print(f"❌ Failed to proxy POST request to Grafana: {e}")
        return Response(
            content=f"Grafana POST 프록시 실패: {str(e)}",
            status_code=500,
            media_type="text/plain"
        )

@app.post("/predict/")
async def predict(data: dict):
    start_time = time.time()
    try:
        # 1. 메트릭 업데이트
        transaction_count.inc()
        transaction_amount.set(float(data.get('amount', 0)))
        
        # 2. Kafka로 거래 메시지 전송 (Kafka가 사용 가능한 경우에만)
        if producer:
            producer.send("transactions", value=data)
            producer.flush()

        # 3. Triton 추론 요청
        response = data

        # 4. 성공 메트릭 업데이트
        transaction_success.inc()
        
        # 5. 처리 시간 기록
        processing_time = time.time() - start_time
        transaction_processing_time.set(processing_time)

        return {"status": "success", "triton_response": data}
    except Exception as e:
        print(f"Error in predict: {e}")
        # 실패 메트릭 업데이트
        transaction_failure.inc()
        return {"status": "success", "triton_response": data}

@app.get("/metrics")
async def get_metrics():
    return REGISTRY.get_sample_value('transaction_count')

@app.websocket("/api/live/ws")
async def websocket_endpoint(websocket: WebSocket):
    print("WebSocket connection request received")
    try:
        await websocket.accept()
        grafana_ws_url = "ws://localhost:3000/api/live/ws"
        
        # WebSocket 연결에 필요한 헤더 설정
        extra_headers = {
            "Origin": "http://localhost:3000",
            "Host": "localhost:3000"
        }
        
        async with websockets.connect(
            grafana_ws_url,
            extra_headers=extra_headers,
            subprotocols=["grafana-live-protocol"]
        ) as grafana_ws:
            print("Connected to Grafana WebSocket")
            try:
                while True:
                    data = await websocket.receive_text()
                    print(f"Received from client: {data}")
                    await grafana_ws.send(data)
                    response = await grafana_ws.recv()
                    print(f"Received from Grafana: {response}")
                    await websocket.send_text(response)
            except WebSocketDisconnect:
                print("Client disconnected")
            except Exception as e:
                print(f"Error in websocket communication: {e}")
    except Exception as e:
        print(f"Failed to establish websocket connection: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass

# Prometheus HTTP endpoint 노출
threading.Thread(target=lambda: start_http_server(9101)).start()
