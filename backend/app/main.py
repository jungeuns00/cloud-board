"""게시판 백엔드 API (FastAPI + PostgreSQL)."""
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

log = logging.getLogger("board")
logging.basicConfig(level=logging.INFO)

DB_DSN = (
    f"host={os.getenv('DB_HOST', 'localhost')} "
    f"port={os.getenv('DB_PORT', '5432')} "
    f"dbname={os.getenv('DB_NAME', 'board')} "
    f"user={os.getenv('DB_USER', 'board')} "
    f"password={os.getenv('DB_PASSWORD', 'board')}"
)
# 서버리스 필터 함수(AWS Lambda Function URL). 비어 있으면 필터링을 건너뛴다.
FILTER_URL = os.getenv("FILTER_URL", "").strip()

pool = ConnectionPool(DB_DSN, min_size=1, max_size=5, open=False, kwargs={"row_factory": dict_row})

# 커스텀 비즈니스 메트릭 (Grafana 대시보드에서 사용)
POSTS_CREATED = Counter("board_posts_created_total", "작성된 게시글 수")
POSTS_UPDATED = Counter("board_posts_updated_total", "수정된 게시글 수")
POSTS_DELETED = Counter("board_posts_deleted_total", "삭제된 게시글 수")
POSTS_FILTERED = Counter("board_posts_filtered_total", "서버리스 필터가 내용을 바꾼 게시글 수")
FILTER_ERRORS = Counter("board_filter_errors_total", "서버리스 필터 호출 실패 수")


def init_db() -> None:
    """DB가 뜰 때까지 재시도하며 테이블을 만든다."""
    for attempt in range(30):
        try:
            with pool.connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS posts (
                        id         SERIAL PRIMARY KEY,
                        title      VARCHAR(200) NOT NULL,
                        content    TEXT NOT NULL,
                        author     VARCHAR(50) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("DB 준비 대기 중 (%s/30): %s", attempt + 1, exc)
            time.sleep(2)
    raise RuntimeError("DB에 연결할 수 없습니다")


@asynccontextmanager
async def lifespan(_: FastAPI):
    pool.open()
    init_db()
    yield
    pool.close()


app = FastAPI(title="Cloud Board API", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


class PostIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    author: str = Field(min_length=1, max_length=50)


class PostUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class Post(BaseModel):
    id: int
    title: str
    content: str
    author: str
    created_at: datetime
    updated_at: datetime


def apply_filter(title: str, content: str) -> tuple[str, str]:
    """서버리스 함수로 욕설을 마스킹한다. 함수 장애 시 원문 그대로 저장한다."""
    if not FILTER_URL:
        return title, content
    try:
        res = httpx.post(FILTER_URL, json={"title": title, "content": content}, timeout=5)
        res.raise_for_status()
        data = res.json()
        if data.get("filtered"):
            POSTS_FILTERED.inc()
        return data.get("title", title), data.get("content", content)
    except Exception as exc:  # noqa: BLE001
        FILTER_ERRORS.inc()
        log.warning("필터 함수 호출 실패: %s", exc)
        return title, content


@app.get("/livez")
def livez():
    """프로세스 생존 확인용. DB 장애 때문에 컨테이너가 재시작되지 않도록 DB를 확인하지 않는다."""
    return {"status": "alive"}


@app.get("/healthz")
def healthz():
    """트래픽 수신 가능 여부(readiness). DB 연결까지 확인한다."""
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/api/posts", response_model=list[Post])
def list_posts():
    with pool.connection() as conn:
        return conn.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()


@app.get("/api/posts/{post_id}", response_model=Post)
def get_post(post_id: int):
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM posts WHERE id = %s", (post_id,)).fetchone()
    if not row:
        raise HTTPException(404, "게시글을 찾을 수 없습니다")
    return row


@app.post("/api/posts", response_model=Post, status_code=201)
def create_post(body: PostIn):
    title, content = apply_filter(body.title, body.content)
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO posts (title, content, author) VALUES (%s, %s, %s) RETURNING *",
            (title, content, body.author),
        ).fetchone()
    POSTS_CREATED.inc()
    return row


@app.put("/api/posts/{post_id}", response_model=Post)
def update_post(post_id: int, body: PostUpdate):
    title, content = apply_filter(body.title, body.content)
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE posts SET title = %s, content = %s, updated_at = now() WHERE id = %s RETURNING *",
            (title, content, post_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "게시글을 찾을 수 없습니다")
    POSTS_UPDATED.inc()
    return row


@app.delete("/api/posts/{post_id}", status_code=204)
def delete_post(post_id: int):
    with pool.connection() as conn:
        cur = conn.execute("DELETE FROM posts WHERE id = %s", (post_id,))
        deleted = cur.rowcount
    if not deleted:
        raise HTTPException(404, "게시글을 찾을 수 없습니다")
    POSTS_DELETED.inc()
