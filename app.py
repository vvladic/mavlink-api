import socket
import asyncio
import mavlink
import uvicorn

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse


class MavTcp:
    RX_BUFFER_SIZE = 1024
    TX_BUFFER_SIZE = 1024

    def __init__(self, host: str = "127.0.0.1", port=5760) -> None:
        self.host = host
        self.port = port
        self.mav = mavlink.MAVLink(None, 253, 0)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.queue = asyncio.Queue(8192)

        # self.queues: dict[int, asyncio.Queue] = {}
        # for msgId in mavlink.mavlink_map.keys():
        #     self.queues.setdefault(msgId, asyncio.Queue())

        print(f"{self} init done")

    async def connect(self):
        try:
            self.socket.connect((self.host, self.port))
            print(f"Connected to {self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to connect to {self.host}:{self.port}")
            print(f"{e}")

    async def reconnect(self):
        await asyncio.sleep(1)
        print(f"Trying to reconnect {self.host}:{self.port}")
        await self.connect()

    async def parse(self):
        while True:
            try:
                data = self.socket.recv(self.RX_BUFFER_SIZE)
                if not data:
                    await asyncio.sleep(0.01)
                    continue
                parsed = self.mav.parse_buffer(data)
                if not parsed:
                    await asyncio.sleep(0.1)
                    continue
                for msg in parsed:
                    if isinstance(msg, mavlink.MAVLink_message):
                        msgId = msg.get_msgId()
                        msgSeq = msg.get_seq()
                        print(msg.msgname, msgId, msgSeq)
                        try:
                            self.queue.put_nowait(msg.to_json())
                        except Exception as e:
                            break
                await asyncio.sleep(0.01)
            except Exception as e:
                print(f"Parsing exception: {e}")
                await self.reconnect()

    async def ping(self):
        while True:
            try:
                print(f"Sending ping message")
                # self.socket.sendall()
                # self.mav.ping_send(time.time_ns(), seq=self.mav.seq, target_system=1, target_component=1)
                # self.mav.request_data_stream_send(1, 1, mavlink.MAVLINK_MSG_ID_BATTERY_STATUS, 1, 1)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Ping exception: {e}")
                await asyncio.sleep(1)

    async def create_generator(self, queue: asyncio.Queue):
        try:
            while True:
                item = await queue.get()
                yield item
        except Exception as e:
            print(e)
            return

    def telemetry(self):
        return self.create_generator(self.queue)


sp = MavTcp("192.168.2.196")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await sp.connect()
    asyncio.get_event_loop().create_task(sp.parse())
    yield
    pass


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=PlainTextResponse)
async def root():
    return "MAVLink API"


@app.get("/telemetry", response_class=PlainTextResponse)
async def telemetry_stream():
    res = EventSourceResponse(sp.telemetry())
    return res


if __name__ == "__main__":
    # uvicorn.run(app, host="0.0.0.0", port=8000)
    uvicorn.run(app, host="0.0.0.0", port=8000)
